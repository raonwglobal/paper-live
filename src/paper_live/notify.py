from __future__ import annotations

import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramNotifier:
    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    def send(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        body = urlencode({"chat_id": self.chat_id, "text": message}).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        with urlopen(request, timeout=10) as response:
            return response.status == 200
