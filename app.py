# bot_hf.py
import os
import json
import asyncio
from threading import Thread
import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from fpdf import FPDF
from flask import Flask

# =================== CONFIG ===================
BOT_TOKEN = "8487392108:AAEziDsOAZLeYyjjPRVGbDyrhWarxWR7QRY:AAHFCQq8HCCK6_borlSOff6jCa4dRVLrXnQ"  # Telegram bot token
ADMIN_USERNAME = "S1ndarovv"  # admin username
USERS_FILE = "users.json"

# HuggingFace Inference API
HF_API_KEY = "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"
HF_MODEL = "OpenAssistant/oasst-sft-6-llm-epoch-3.5"

# =================== USER DATA ===================
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
else:
    users = {}

def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def ensure_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "free_count": 0,
            "package_remaining": 0,
            "is_premium": False,
            "settings": {"length": "o'rta", "format": "oddiy", "lang": "uz", "add_image": False},
            "state": None
        }
        save_users()
    return users[uid]

# =================== WEB SERVER (keep_alive) ===================
app = Flask('')
@app.route('/')
def home():
    return "Bot ishlayapti"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# =================== HUGGINGFACE API ===================
async def hf_generate(prompt: str) -> str:
    """ HuggingFace modeli orqali matn generatsiya qiladi """
    url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_length": 1200,
            "temperature": 0.7
        }
    }

    def sync_call():
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=40)
            if response.status_code != 200:
                return f"Xatolik: HF API {response.status_code} → {response.text}"
            data = response.json()
            return data[0]["generated_text"]
        except Exception as e:
            return f"Xatolik: {e}"

    return await asyncio.to_thread(sync_call)

# =================== PDF CREATOR ===================
def create_pdf_text(user_id, title, text, add_image=False):
    filename = f"referat_{user_id}_{int(asyncio.get_event_loop().time())}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Mavzu: {title}", ln=True)
    pdf.ln(4)
    pdf.multi_cell(0, 8, text)
    pdf.output(filename)
    return filename

# =================== MENUS ===================
def main_menu_keyboard():
    kb = [
        [InlineKeyboardButton("Taqdimot", callback_data="menu_presentation"),
         InlineKeyboardButton("Mustaqil ish", callback_data="menu_indep")],
        [InlineKeyboardButton("Referat", callback_data="menu_referat"),
         InlineKeyboardButton("Mening hisobim", callback_data="menu_account")],
        [InlineKeyboardButton("To'lov qilish", callback_data="menu_pay"),
         InlineKeyboardButton("Yordam", callback_data="menu_help")],
        [InlineKeyboardButton("Sozlamalar", callback_data="menu_settings"),
         InlineKeyboardButton("Biz bilan bog'lanish", callback_data="menu_contact")]
    ]
    return InlineKeyboardMarkup(kb)

# =================== CALLBACK HANDLERS ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)
    await update.message.reply_text(
        f"Salom, {user.first_name}! Botga xush kelibsiz.\nSiz 3 ta bepul referat olishingiz mumkin.",
        reply_markup=main_menu_keyboard()
    )

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user = ensure_user(uid)

    if query.data == "menu_referat":
        user['state'] = "await_referat_topic"
        save_users()
        await query.edit_message_text("Referat mavzusini kiriting.")

    elif query.data == "menu_indep":
        user['state'] = "await_indep_topic"
        save_users()
        await query.edit_message_text("Mustaqil ish mavzusini yuboring.")

    elif query.data == "menu_account":
        await query.edit_message_text(
            f"Hisobingiz:\nBepul: {user['free_count']}/3\nPaket qoldi: {user['package_remaining']}",
            reply_markup=main_menu_keyboard()
        )

    elif query.data == "menu_help":
        await query.edit_message_text("Yordam: Mavzu yuboring va bot tayyorlab beradi.",
                                      reply_markup=main_menu_keyboard())

    else:
        await query.edit_message_text("Asosiy menyu", reply_markup=main_menu_keyboard())

# =================== MESSAGE HANDLER ===================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = ensure_user(uid)
    text = update.message.text.strip()
    state = user.get("state")

    if state in ("await_referat_topic", "await_indep_topic"):
        topic = text
        await update.message.reply_text("Referat tayyorlanmoqda...")

        # Prompt yaratish
        settings = user["settings"]
        prompt = (
            f"Referat yozing.\n"
            f"Til: {settings['lang']}\n"
            f"Uzunlik: {settings['length']}\n"
            f"Format: {settings['format']}\n"
            f"Mavzu: {topic}\n"
            f"Kirish, asosiy qism va xulosa bo'lsin."
        )

        answer = await hf_generate(prompt)

        if answer.startswith("Xatolik"):
            await update.message.reply_text(answer)
            user["state"] = None
            save_users()
            return

        pdf_file = create_pdf_text(uid, topic, answer)

        await update.message.reply_document(open(pdf_file, "rb"))

        # Limitlarni hisoblash
        if not user["is_premium"]:
            if user["free_count"] < 3:
                user["free_count"] += 1
            elif user["package_remaining"] > 0:
                user["package_remaining"] -= 1

        user["state"] = None
        save_users()

        os.remove(pdf_file)
        return

    await update.message.reply_text("Asosiy menyu:", reply_markup=main_menu_keyboard())

# =================== MAIN ===================
def main():
    keep_alive()
    bot = ApplicationBuilder().token(BOT_TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(menu_callback))
    bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    bot.run_polling()

if __name__ == "__main__":
    main()