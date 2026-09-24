import os, json, logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

DATA_FILE = Path("data.json")
logging.basicConfig(level=logging.INFO)

def load_data():
    return json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []

def find_rate(item, stage):
    for row in load_data():
        if row["item"].strip().lower() == item.strip().lower() and row["stage"].strip().lower() == stage.strip().lower():
            return row["daily_target"]
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً 👋\nأرسل صورة كرت الإنتاج 📸.\n"
        "النسخة التجريبية ستتعامل مع الصنف + المرحلة/المكنة، "
        "وتستخدم جدول المعدلات الموجود في data.json."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل صورة كرت الإنتاج 📸")

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "وصلت الصورة ✅\n"
        "الاتصال بتيليغرام جاهز. الخطوة التالية هي ربط قراءة بيانات الكرت بالصورة وجدول المعدلات."
    )

async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل صورة كرت الإنتاج 📸")

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN غير موجود")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    app.run_polling()

if __name__ == "__main__":
    main()
