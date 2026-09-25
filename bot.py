import os
import json
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

DATA_FILE = Path("data.json")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def load_data():
    if not DATA_FILE.exists():
        return []

    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def find_rate(item, stage):
    item = item.strip().lower()
    stage = stage.strip().lower()

    for row in load_data():
        row_item = str(row.get("item", "")).strip().lower()
        row_stage = str(row.get("stage", "")).strip().lower()

        if row_item == item and row_stage == stage:
            return row.get("daily_target")

    return None


def find_rates_for_item(item):
    item = item.strip().lower()
    results = []

    for row in load_data():
        if str(row.get("item", "")).strip().lower() == item:
            results.append(row)

    return results


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً 👋\n\n"
        "هاي النسخة التجريبية من بوت الإنتاج.\n\n"
        "للتجربة أرسل:\n"
        "/test\n\n"
        "وبعدين البوت رح يطلب منك الصنف والمرحلة والكمية.\n\n"
        "ملاحظة: المعدل اليومي في جدولنا محسوب بالدزينة، "
        "وليس بالقطعة."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "الأوامر المتاحة:\n"
        "/start — بدء البوت\n"
        "/test — تجربة حساب الإنتاج\n"
        "/rate — البحث عن معدل صنف ومرحلة"
    )


async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["test_step"] = "item"
    await update.message.reply_text(
        "تمام 👍\nأرسل اسم الصنف كما هو موجود بجدول المعدلات."
    )


async def rate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace("/rate", "", 1).strip()

    if "|" not in text:
        await update.message.reply_text(
            "اكتب الأمر بهذا الشكل:\n"
            "/rate اسم الصنف | المرحلة"
        )
        return

    item, stage = [x.strip() for x in text.split("|", 1)]
    rate = find_rate(item, stage)

    if rate is None:
        await update.message.reply_text(
            "ما لقيت تطابق مطابق تمامًا بجدول المعدلات ❌\n\n"
            f"الصنف: {item}\n"
            f"المرحلة: {stage}"
        )
        return

    await update.message.reply_text(
        f"تم العثور على المعدل ✅\n\n"
        f"الصنف: {item}\n"
        f"المرحلة: {stage}\n"
        f"المعدل اليومي: {rate} دزينة\n"
        f"أي {rate * 12} قطعة باليوم."
    )


async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()
    step = context.user_data.get("test_step")

    if not step:
        await update.message.reply_text(
            "استخدم /test لبدء تجربة الحساب، "
            "أو /rate للبحث عن معدل."
        )
        return

    if step == "item":
        context.user_data["test_item"] = message

        matches = find_rates_for_item(message)

        if not matches:
            await update.message.reply_text(
                "ما لقيت هذا الصنف بجدول التجربة ❌\n"
                "جرّب كتابة الاسم مرة ثانية كما هو موجود بالجدول."
            )
            return

        context.user_data["test_step"] = "stage"

        stages = []
        for row in matches:
            stage = row.get("stage")
            if stage and stage not in stages:
                stages.append(stage)

        await update.message.reply_text(
            "تمام ✅\n"
            "هلق أرسل اسم المرحلة/المكنة.\n\n"
            "المراحل الموجودة لهذا الصنف:\n"
            + "\n".join(f"• {s}" for s in stages)
        )
        return

    if step == "stage":
        context.user_data["test_stage"] = message

        item = context.user_data["test_item"]
        rate = find_rate(item, message)

        if rate is None:
            await update.message.reply_text(
                "ما لقيت تطابق بين الصنف والمرحلة ❌\n"
                "جرّب كتابة المرحلة تمامًا كما ظهرت بالقائمة."
            )
            return

        context.user_data["test_rate"] = rate
        context.user_data["test_step"] = "quantity"

        await update.message.reply_text(
            f"المعدل اليومي هو: {rate} دزينة ✅\n"
            f"يعني: {rate * 12} قطعة باليوم.\n\n"
            "هلق أرسل الكمية التي اشتغلها العامل بالدزينة."
        )
        return

    if step == "quantity":
        try:
            quantity = float(message.replace(",", "."))
        except ValueError:
            await update.message.reply_text(
                "اكتب الكمية كرقم فقط، مثل: 20"
            )
            return

        rate = float(context.user_data["test_rate"])
        percentage = (quantity / rate * 100) if rate else 0

        await update.message.reply_text(
            "تم الحساب ✅\n\n"
            f"الصنف: {context.user_data['test_item']}\n"
            f"المرحلة: {context.user_data['test_stage']}\n"
            f"المعدل اليومي: {rate:g} دزينة\n"
            f"إنتاج العامل: {quantity:g} دزينة\n"
            f"نسبة الإنجاز: {percentage:.1f}%\n\n"
            "هاي نسخة تجريبية فقط. لاحقًا منربطها بكرت الإنتاج "
            "والكرت الأساسي وقراءة الصورة."
        )

        context.user_data.clear()
        return


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "وصلت الصورة 📸✅\n\n"
        "النسخة الحالية تجريبية، ولسه ما فعلنا قراءة البيانات "
        "من الصورة تلقائيًا.\n"
        "حاليًا جرّب الحساب باستخدام /test."
    )


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN غير موجود")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CommandHandler("rate", rate_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))

    app.run_polling()


if __name__ == "__main__":
    main()
