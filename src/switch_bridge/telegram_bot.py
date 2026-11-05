import os
import sys
import time
import requests
from pathlib import Path
from typing import Optional, Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import settings
from src.switch_bridge.webhook_handler import SwitchWebhookRouter
from src.db.session import SessionLocal
from src.db.models import Shop

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class TelegramBotRunner:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.api_base = f"https://api.telegram.org/bot{self.token}" if self.token else None
        self.router = SwitchWebhookRouter()
        self.last_update_id = 0

    def is_configured(self) -> bool:
        return bool(self.token and len(self.token) > 10)

    def send_message(self, chat_id: int | str, text: str) -> bool:
        if not self.is_configured():
            print(f"[Telegram Mock Send -> {chat_id}]: {text[:80]}...")
            return True

        url = f"{self.api_base}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        try:
            res = requests.post(url, json=payload, timeout=10)
            return res.status_code == 200
        except Exception as e:
            print(f"Error sending message to Telegram: {e}")
            return False

    def download_telegram_file(self, file_id: str, dest_filename: str) -> Optional[Path]:
        if not self.is_configured():
            return None

        try:
            get_file_url = f"{self.api_base}/getFile?file_id={file_id}"
            file_info = requests.get(get_file_url, timeout=10).json()
            if not file_info.get("ok"):
                return None

            file_path = file_info["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

            dest_path = UPLOAD_DIR / dest_filename
            with requests.get(download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            return dest_path
        except Exception as e:
            print(f"Error downloading file from Telegram: {e}")
            return None

    def resolve_room(self, chat_id: int | str, chat_title: str = "") -> str:
        db = SessionLocal()
        try:
            shop = db.query(Shop).filter(Shop.telegram_chat_id == str(chat_id)).first()
            if shop:
                return shop.id
            if "ca" in chat_title.lower() or "office" in chat_title.lower():
                return "ca-office"
            return "shop-sharma-kirana"
        finally:
            db.close()

    def process_update(self, update: dict[str, Any]) -> list[dict[str, Any]]:
        message = update.get("message")
        if not message:
            return []

        chat_id = message["chat"]["id"]
        chat_title = message["chat"].get("title", "")
        user_name = message.get("from", {}).get("first_name", "User")
        text = message.get("text") or message.get("caption") or ""
        room_name = self.resolve_room(chat_id, chat_title)

        attachment_path = None
        if "document" in message:
            doc = message["document"]
            filename = doc.get("file_name", "invoice.pdf")
            file_id = doc["file_id"]
            downloaded = self.download_telegram_file(file_id, f"tg_{chat_id}_{filename}")
            if downloaded:
                attachment_path = str(downloaded)

        elif "photo" in message:
            photos = message["photo"]
            best_photo = photos[-1]
            file_id = best_photo["file_id"]
            downloaded = self.download_telegram_file(file_id, f"tg_{chat_id}_receipt.png")
            if downloaded:
                attachment_path = str(downloaded)

        if text.strip() in ["/start", "/help"]:
            help_text = (
                f"Namaste {user_name}! I am MunimJi, your AI GST & Bookkeeping Assistant.\n\n"
                f"Available Commands:\n"
                f"- Drop any Bill Photo or PDF invoice to automatically read and audit GST compliance\n"
                f"- 'OK': Confirm details of the latest uploaded bill\n"
                f"- /khata: View your current month's Accounts Book (Mal Kharid & Expenses)\n"
                f"- /tax_savings: Junior CA advice on Section 32 depreciation & personal tax savings\n"
                f"- /presumptive [turnover]: Check Section 44AD presumptive tax savings\n"
                f"- /status: View count of clean vs pending bills\n"
                f"- /dashboard & /summary (for CA room): Review cross-shop ITC and GSTR returns"
            )
            self.send_message(chat_id, help_text)
            return [{"room": room_name, "text": help_text}]

        events = self.router.handle_message(
            room_name=room_name,
            user_name=user_name,
            text=text,
            attachment_path=attachment_path,
        )

        for evt in events:
            self.send_message(chat_id, f"[{evt['sender']}]:\n{evt['text']}")

        return events

    def start_polling(self, max_iterations: Optional[int] = None):
        if not self.is_configured():
            print("Telegram Bot Token is not configured.")
            print("To connect live Telegram groups:")
            print("1. Message @BotFather on Telegram and create a new bot to get a token.")
            print("2. Set TELEGRAM_BOT_TOKEN=your_token in .env")
            print("3. Run: python src/switch_bridge/telegram_bot.py")
            return

        print(f"MunimJi Telegram Bot is live and listening...")
        offset = 0
        iteration = 0

        while True:
            if max_iterations and iteration >= max_iterations:
                break
            iteration += 1

            try:
                url = f"{self.api_base}/getUpdates?timeout=25&offset={offset}"
                res = requests.get(url, timeout=30)
                if res.status_code == 200:
                    data = res.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        self.process_update(update)
            except Exception as e:
                print(f"Polling warning: {e}")
                time.sleep(3)


if __name__ == "__main__":
    runner = TelegramBotRunner()
    runner.start_polling()

