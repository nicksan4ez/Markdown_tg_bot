import logging
import os
import re
from typing import Any, Dict, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request


logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
BASE_URL = os.getenv("BASE_URL")

for env_name, value in (
    ("BOT_TOKEN", BOT_TOKEN),
    ("WEBHOOK_SECRET", WEBHOOK_SECRET),
    ("TARGET_CHAT_ID", TARGET_CHAT_ID),
):
    if not value:
        raise RuntimeError(f"Environment variable {env_name} is required.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!\\"
_ESCAPE_PATTERN = re.compile(f"([{re.escape(MARKDOWN_V2_SPECIAL_CHARS)}])")
_TOKEN_PATTERN = re.compile(
    r"(?P<bold>\*\*(?P<bold_text>.+?)\*\*)|(?P<url>https?://\S+)", re.IGNORECASE
)

app = FastAPI()


def escape_markdown_v2(text: str) -> str:
    """Escape characters that have special meaning in MarkdownV2."""
    return _ESCAPE_PATTERN.sub(r"\\\1", text)


def format_for_markdown_v2(text: str) -> str:
    """
    Prepare text for Telegram MarkdownV2:
    - escape special characters
    - make bare URLs clickable
    - support **bold** (converted to Telegram *bold*)
    """
    result: list[str] = []
    last_index = 0

    for match in _TOKEN_PATTERN.finditer(text):
        start, end = match.span()
        if start > last_index:
            result.append(escape_markdown_v2(text[last_index:start]))

        url = match.group("url")
        bold_text = match.group("bold_text")

        if url:
            display = escape_markdown_v2(url)
            result.append(f"[{display}]({url})")
        elif bold_text:
            inner = escape_markdown_v2(bold_text)
            result.append(f"*{inner}*")

        last_index = end

    if last_index < len(text):
        result.append(escape_markdown_v2(text[last_index:]))

    return "".join(result)


async def forward_text_to_chat(text: str) -> None:
    if not text:
        return

    payload = {
        "chat_id": TARGET_CHAT_ID,
        "text": format_for_markdown_v2(text),
        "parse_mode": "MarkdownV2",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(TELEGRAM_API_URL, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logging.exception("Failed to send message to Telegram: %s", exc)


def extract_text(update: Dict[str, Any]) -> Optional[str]:
    """Extract text or caption from common Telegram update payloads."""
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        message: Optional[Dict[str, Any]] = update.get(key)
        if not message:
            continue
        if "text" in message:
            return str(message["text"])
        if "caption" in message:
            return str(message["caption"])
    return None


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks) -> Dict[str, bool]:
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    update = await request.json()
    text = extract_text(update)

    if text:
        background_tasks.add_task(forward_text_to_chat, text)

    return {"ok": True}
