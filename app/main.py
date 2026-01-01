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
    r"|(?P<code>`(?P<code_text>[^`]+)`)"
    r"|(?P<bold>\*\*(?P<bold_text>.+?)\*\*)"
    r"|(?P<italic>(?<!\*)\*(?P<italic_text>[^*\n]+?)\*(?!\*))"
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


def escape_markdown_v2_code(text: str) -> str:
    """Escape characters that have special meaning in MarkdownV2 code spans."""
    return text.replace("\\", "\\\\").replace("`", "\\`")


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
        italic_text = match.group("italic_text")
        code_text = match.group("code_text")

        if link_text and link_url:
            display = escape_markdown_v2(link_text)
            result.append(f"[{display}]({escape_markdown_v2_url(link_url)})")
        elif code_text:
            inner = escape_markdown_v2_code(code_text)
            result.append(f"`{inner}`")
        elif url:
            display = escape_markdown_v2(url)
            result.append(f"[{display}]({escape_markdown_v2_url(url)})")
        elif bold_text:
            inner = escape_markdown_v2(bold_text)
            result.append(f"*{inner}*")
        elif italic_text:
            inner = escape_markdown_v2(italic_text)
            result.append(f"_{inner}_")

        last_index = end

    if last_index < len(text):
        result.append(escape_markdown_v2(text[last_index:]))

    return "".join(result)


def _format_line(content: str) -> str:
    stripped = content.strip()
    if stripped == "---":
        return r"\=\=\=\=\=\=\=\=\=\="
    if content.startswith("# "):
        inner = _format_inline(content[2:].lstrip())
        return f"__*{inner}*__"
    if content.startswith("## "):
        inner = _format_inline(content[3:].lstrip())
        return f"*{inner}*"
    if content.startswith("### "):
        inner = _format_inline(content[4:].lstrip())
        return f"__{inner}__"
    if content.startswith(("- ", "* ")):
        rest = content[2:]
        return f"— {_format_inline(rest)}"
    return _format_inline(content)


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

        formatted_lines.append(f"{_format_line(content)}{newline}")

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


def format_sender(sender: Dict[str, Any], chat_id: int) -> str:
    username = sender.get("username")
    first_name = sender.get("first_name")
    last_name = sender.get("last_name")

    name_parts = [part for part in (first_name, last_name) if part]
    display = " ".join(name_parts).strip()

    if username:
        if display:
            display = f"{display} (@{username})"
        else:
            display = f"@{username}"

    return display or f"user {chat_id}"


def format_log_entry(kind: str, chat_id: int, sender: Dict[str, Any], formatted_text: str) -> str:
    prefix = f"{kind} {format_sender(sender, chat_id)} ({chat_id})"
    return f"{escape_markdown_v2(prefix)}\n{formatted_text}"


def _utf16_offset_to_index(text: str, offset: int) -> int:
    count = 0
    for index, ch in enumerate(text):
        if count >= offset:
            return index
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def apply_entities(text: str, entities: Optional[list[Dict[str, Any]]]) -> str:
    if not entities or "**" in text or "*" in text:
        return text

    inserts: list[tuple[int, str]] = []
    for entity in entities:
        entity_type = entity.get("type")
        if entity_type not in {"bold", "italic"}:
            continue
        offset = entity.get("offset")
        length = entity.get("length")
        if not isinstance(offset, int) or not isinstance(length, int):
            continue
        start = _utf16_offset_to_index(text, offset)
        end = _utf16_offset_to_index(text, offset + length)
        marker = "**" if entity_type == "bold" else "*"
        inserts.append((end, marker))
        inserts.append((start, marker))

    if not inserts:
        return text

    inserts.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    result = text
    for position, marker in inserts:
        result = result[:position] + marker + result[position:]
    return result


async def handle_message(chat_id: int, sender: Dict[str, Any], text: str) -> None:
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

    log_in = format_log_entry("IN", chat_id, sender, formatted)
    await send_chunks(LOGS_CHAT_ID_INT, split_message(log_in))
    await send_chunks(chat_id, chunks)
    log_out = format_log_entry("OUT", chat_id, sender, formatted)
    await send_chunks(LOGS_CHAT_ID_INT, split_message(log_out))


def extract_message(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get the message object from common Telegram update payloads."""
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        message = update.get(key)
        if message:
            return message
    return None


def extract_text_and_entities(
    message: Dict[str, Any],
) -> tuple[Optional[str], Optional[list[Dict[str, Any]]]]:
    """Extract text/caption and entities from a Telegram message."""
    if "text" in message:
        return str(message["text"]), message.get("entities")
    if "caption" in message:
        return str(message["caption"]), message.get("caption_entities")
    return None, None


def extract_chat_info(message: Dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    """Get chat_id and chat_type from a Telegram message."""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    if chat_id is not None:
        try:
            return int(chat_id), str(chat_type) if chat_type is not None else None
        except (TypeError, ValueError):
            return None, str(chat_type) if chat_type is not None else None
    return None, str(chat_type) if chat_type is not None else None


def extract_sender(message: Dict[str, Any]) -> Dict[str, Any]:
    """Get sender details from a Telegram message."""
    sender = message.get("from") or {}
    return {
        "id": sender.get("id"),
        "username": sender.get("username"),
        "first_name": sender.get("first_name"),
        "last_name": sender.get("last_name"),
    }


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
    message = extract_message(update)
    if not message:
        return {"ok": True}

    text, entities = extract_text_and_entities(message)
    chat_id, chat_type = extract_chat_info(message)
    sender = extract_sender(message)

    if chat_type != "private":
        return {"ok": True}

    if text and chat_id is not None:
        text = apply_entities(text, entities)
        background_tasks.add_task(handle_message, chat_id, sender, text)

    return {"ok": True}
