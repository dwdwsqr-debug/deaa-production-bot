import os
import json
import logging
import asyncio
import re
from pathlib import Path
from io import BytesIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

import requests
from PIL import Image

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

DATA_FILE = Path("data.json")
OCR_API_KEY = os.environ.get("OCR_API_KEY")

logging.basicConfig(level=logging.INFO)


def load_data():
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def find_rate(item, stage):
    item = item.strip().lower()
    stage = stage.strip().lower()

    for row in load_data():
        if (
            row["item"].strip().lower() == item
            and row["stage"].strip().lower() == stage
        ):
            return row["daily_target"]

    return None


def normalize_digits(text):
    trans = str.maketrans(
        "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
        "01234567890123456789",
    )
    return text.translate(trans)


def prepare_image(raw_bytes):
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")

    max_size = 1800
    img.thumbnail((max_size, max_size))

    for quality in (85, 75, 65, 55, 45):
        output = BytesIO()
        img.save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
        )

        if output.tell() <= 900000:
            return output.getvalue()

    return output.getvalue()


def ocr_image(image_bytes):
    if not OCR_API_KEY:
        raise RuntimeError("OCR_API_KEY غير موجود في Render")

    url = "https://api.ocr.space/parse/image"

    headers = {
        "apikey": OCR_API_KEY,
    }

    files = {
        "file": ("card.jpg", image_bytes, "image/jpeg"),
    }

    data = {
        "language": "ara",
        "isTable": "true",
        "OCREngine": "3",
        "isOverlayRequired": "false",
    }

    response = requests.post(
        url,
        headers=headers,
        files=files,
        data=data,
        timeout=90,
    )

    response.raise_for_status()

    result = response.json()

    if result.get("IsErroredOnProcessing"):
        raise RuntimeError(
            str(result.get("ErrorMessage", "فشل OCR"))
        )

    texts = []

    for item in result.get("ParsedResults", []):
        texts.append(item.get("ParsedText", ""))

    return "\n".join(texts).strip()


def extract_rows(text):
    """
    محاولة قراءة صفوف جدول كرت العامل.
    هذه نسخة تجريبية، ولن تخترع قيمة إذا لم تكن واضحة.
    """

    rows = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        if "|" not in line:
            continue

        cells = [
            c.strip()
            for c in line.split("|")
            if c.strip()
        ]

        if len(cells) < 5:
            continue

        # تجاهل سطر فاصل Markdown
        if all(
            re.fullmatch(r"[-:_\s]+", c or "")
            for c in cells
        ):
            continue

        cells = [normalize_digits(c) for c in cells]

        # نحتاج على الأقل رقم كرت وكمية رقمية
        card_numbers = re.findall(r"\d+", cells[0])
        quantities = re.findall(r"\d+(?:[.,]\d+)?", cells[-1])

        if not card_numbers or not quantities:
            continue

        card_number = card_numbers[0]
        quantity = quantities[-1].replace(",", ".")

        rows.append(
            {
                "card_number": card_number,
                "item": cells[1] if len(cells) > 1 else "[غير واضح]",
                "size": cells[2] if len(cells) > 2 else "[غير واضح]",
                "stage": cells[3] if len(cells) > 3 else "[غير واضح]",
                "quantity": quantity,
            }
        )

    return rows


def calculate_rows(rows):
    results = []

    for row in rows:
        item = row["item"]
        stage = row["stage"]

        rate = find_rate(item, stage)

        if rate is None:
            row["daily_target"] = None
            row["completion"] = None
            row["status"] = "المعدل غير موجود في data.json"
            results.append(row)
            continue

        try:
            quantity = float(row["quantity"])
            target = float(rate)

            completion = (quantity / target) * 100

            row["daily_target"] = target
            row["completion"] = round(completion, 1)
            row["status"] = "تم الحساب"

        except Exception:
            row["daily_target"] = None
            row["completion"] = None
            row["status"] = "الكمية غير واضحة"

        results.append(row)

    return results


def format_results(ocr_text, results):
    message = "📸 قراءة كرت الإنتاج\n\n"

    if not ocr_text:
        return (
            "❌ لم أستطع قراءة الكتابة من الصورة.\n"
            "جرّب تصوير الكرت بإضاءة أقوى ومن دون ميلان."
        )

    if not results:
        message += "⚠️ تمت قراءة الصورة، لكن لم أستطع استخراج الصفوف بشكل جدول.\n\n"
        message += "النص الذي قرأه النظام:\n"
        message += "────────────\n"
        message += ocr_text[:3500]
        return message

    message += f"تم استخراج {len(results)} صف/صفوف.\n\n"

    for i, row in enumerate(results, 1):
        message += f"🔹 الصف {i}\n"
        message += f"الكرت: {row['card_number']}\n"
        message += f"الصنف: {row['item']}\n"
        message += f"القياس: {row['size']}\n"
        message += f"العمل: {row['stage']}\n"
        message += f"الكمية: {row['quantity']} د\n"

        if row["daily_target"] is not None:
            message += (
                f"المعدل اليومي: {row['daily_target']} د\n"
                f"نسبة الإنجاز: {row['completion']}%\n"
                f"المعدل بالقطع: {row['daily_target'] * 12:g} قطعة/يوم\n"
            )
        else:
            message += f"⚠️ {row['status']}\n"

        message += "\n"

    return message[:3900]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً 👋\n"
        "أرسل صورة كرت الإنتاج 📸\n\n"
        "سأحاول قراءة الكرت وحساب الإنتاج اعتماداً على data.json."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 أرسل صورة كرت الإنتاج."
    )


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "📥 وصلت الصورة.\n"
            "جاري قراءة الكرت وحساب الإنتاج... ⏳"
        )

        photo_file = update.message.photo[-1]

        telegram_file = await context.bot.get_file(
            photo_file.file_id
        )

        raw_bytes = bytes(
            await telegram_file.download_as_bytearray()
        )

        image_bytes = prepare_image(raw_bytes)

        ocr_text = await asyncio.to_thread(
            ocr_image,
            image_bytes,
        )

        rows = extract_rows(ocr_text)
        results = calculate_rows(rows)

        message = format_results(
            ocr_text,
            results,
        )

        await update.message.reply_text(message)

    except Exception as e:
        logging.exception("Photo processing error")

        await update.message.reply_text(
            "❌ حصل خطأ أثناء قراءة الصورة.\n\n"
            f"التفاصيل: {str(e)[:500]}"
        )


async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 أرسل صورة كرت الإنتاج، وليس نصاً."
    )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_health_server():
    port = int(os.environ.get("PORT", "10000"))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )

    server.serve_forever()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN غير موجود"
        )

    threading.Thread(
        target=run_health_server,
        daemon=True,
    ).start()

    app = (
        Application.builder()
        .token(token)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_cmd)
    )

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text,
        )
    )

    app.run_polling()


if __name__ == "__main__":
    main()
