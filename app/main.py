import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


logging.basicConfig(level=logging.INFO)

if load_dotenv:
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
LOGS_CHAT_ID = os.getenv("LOGS_CHAT_ID")
BASE_URL = os.getenv("BASE_URL")
DRY_RUN = os.getenv("DRY_RUN", "").lower() in {"1", "true", "yes"}

for env_name, value in (
    ("BOT_TOKEN", BOT_TOKEN),
    ("WEBHOOK_SECRET", WEBHOOK_SECRET),
    ("LOGS_CHAT_ID", LOGS_CHAT_ID),
):
    if not value:
        raise RuntimeError(f"Environment variable {env_name} is required.")

try:
    LOGS_CHAT_ID_INT = int(LOGS_CHAT_ID)
except (TypeError, ValueError) as exc:
    raise RuntimeError("Environment variable LOGS_CHAT_ID must be an integer.") from exc

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!\\"
_ESCAPE_PATTERN = re.compile(f"([{re.escape(MARKDOWN_V2_SPECIAL_CHARS)}])")
_URL_ESCAPE_PATTERN = re.compile(r"([)\\])")
_TOKEN_PATTERN = re.compile(
    r"(?P<link>\[(?P<link_text>[^\]]+)\]\((?P<link_url>https?://[^\s)]+)\))"
    r"|(?P<bold>\*\*(?P<bold_text>.+?)\*\*)"
    r"|(?P<url>https?://\S+)",
    re.IGNORECASE,
)

app = FastAPI()


def escape_markdown_v2(text: str) -> str:
    """Escape characters that have special meaning in MarkdownV2."""
    return _ESCAPE_PATTERN.sub(r"\\\1", text)


def escape_markdown_v2_url(url: str) -> str:
    """Escape characters that have special meaning in MarkdownV2 URLs."""
    return _URL_ESCAPE_PATTERN.sub(r"\\\1", url)


def _format_inline(text: str) -> str:
    """Escape text and convert basic inline tokens (bold, links, bare URLs)."""
    result: list[str] = []
    last_index = 0

    for match in _TOKEN_PATTERN.finditer(text):
        start, end = match.span()
        if start > last_index:
            result.append(escape_markdown_v2(text[last_index:start]))

        link_text = match.group("link_text")
        link_url = match.group("link_url")
        url = match.group("url")
        bold_text = match.group("bold_text")

        if link_text and link_url:
            display = escape_markdown_v2(link_text)
            result.append(f"[{display}]({escape_markdown_v2_url(link_url)})")
        elif url:
            display = escape_markdown_v2(url)
            result.append(f"[{display}]({escape_markdown_v2_url(url)})")
        elif bold_text:
            inner = escape_markdown_v2(bold_text)
            result.append(f"*{inner}*")

        last_index = end

    if last_index < len(text):
        result.append(escape_markdown_v2(text[last_index:]))

    return "".join(result)


def format_for_markdown_v2(text: str) -> str:
    """
    Prepare text for Telegram MarkdownV2:
    - escape special characters
    - make bare URLs clickable
    - support **bold** (converted to Telegram *bold*)
    - keep line breaks intact
    """
    lines = text.splitlines(keepends=True)
    formatted_lines: list[str] = []

    for line in lines:
        newline = ""
        content = line
        if line.endswith("\r\n"):
            content = line[:-2]
            newline = "\r\n"
        elif line.endswith("\n") or line.endswith("\r"):
            content = line[:-1]
            newline = line[-1]

        formatted_lines.append(f"{_format_inline(content)}{newline}")

    return "".join(formatted_lines)


async def send_chunks(chat_id: int, chunks: list[str]) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "MarkdownV2",
            }

            try:
                response = await client.post(TELEGRAM_API_URL, json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logging.error(
                    "Telegram API error: chat_id=%s status=%s body=%s",
                    chat_id,
                    exc.response.status_code,
                    exc.response.text,
                )
                break
            except httpx.HTTPError as exc:
                logging.exception("Failed to send message to Telegram: %s", exc)
                break


async def handle_message(chat_id: int, text: str) -> None:
    formatted = format_for_markdown_v2(text)
    chunks = split_message(formatted)

    if DRY_RUN:
        logging.info(
            "DRY_RUN enabled. chat_id=%s logs_chat_id=%s formatted_text=%s",
            chat_id,
            LOGS_CHAT_ID_INT,
            formatted,
        )
        return

    await send_chunks(LOGS_CHAT_ID_INT, chunks)
    await send_chunks(chat_id, chunks)
    await send_chunks(LOGS_CHAT_ID_INT, chunks)


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


def extract_chat_id(update: Dict[str, Any]) -> Optional[int]:
    """Get chat_id from common Telegram update payloads."""
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        message: Optional[Dict[str, Any]] = update.get(key)
        if not message:
            continue
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is not None:
            try:
                return int(chat_id)
            except (TypeError, ValueError):
                return None
    return None


def split_message(text: str, limit: int = 4096) -> list[str]:
    """Split text into Telegram-sized chunks, preferring line boundaries."""
    chunks: list[str] = []
    current = ""

    for line in text.splitlines(keepends=True):
        if len(current) + len(line) <= limit:
            current += line
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(line) <= limit:
            current = line
        else:
            start = 0
            while start < len(line):
                end = min(start + limit, len(line))
                chunks.append(line[start:end])
                start = end

    if current:
        chunks.append(current)

    return chunks


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
    chat_id = extract_chat_id(update)

    if text and chat_id is not None:
        background_tasks.add_task(handle_message, chat_id, text)

    return {"ok": True}
