# Markdown Telegram Bot

Telegram-бот на FastAPI для Render Web Service. Работает как эхо-бот: принимает сообщения, конвертирует Markdown в формат Telegram MarkdownV2 и отправляет ответ обратно пользователю. Все входящие сообщения и ответы бота копируются в отдельный чат логов.

## Переменные окружения

- `BOT_TOKEN` — токен бота.
- `WEBHOOK_SECRET` — секрет для заголовка `X-Telegram-Bot-Api-Secret-Token`.
- `LOGS_CHAT_ID` — chat_id чата логов, куда копировать входящие и исходящие сообщения.
- `BASE_URL` — публичный URL сервиса (например, `https://<service>.onrender.com`), опционально.

## Локальный запуск

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
export PORT=8000  # Windows: set PORT=8000
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Проверка здоровья:

```bash
curl http://localhost:8000/healthz
```

## Render (Web Service)

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Env Vars: `BOT_TOKEN`, `WEBHOOK_SECRET`, `LOGS_CHAT_ID`, `BASE_URL` (опционально)

## Установка webhook

```bash
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" ^
  -H "Content-Type: application/json" ^
  -d "{\"url\": \"${BASE_URL}/telegram/webhook\", \"secret_token\": \"${WEBHOOK_SECRET}\"}"
```

Проверка статуса:

```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

## Тест локально

```bash
curl -X POST http://localhost:8000/telegram/webhook ^
  -H "Content-Type: application/json" ^
  -H "X-Telegram-Bot-Api-Secret-Token: $WEBHOOK_SECRET" ^
  -d "{\"message\":{\"chat\":{\"id\":123},\"text\":\"# Title\\n## Subtitle\\nText https://example.com **bold**\"}}"
```

Замените `id:123` на реальный chat_id отправителя. В лог-чат попадут и входящее сообщение, и ответ бота.
