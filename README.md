# Markdown Telegram Bot

Телеграм-бот на FastAPI, принимающий webhook и пересылающий текстовые сообщения в указанный чат с форматированием MarkdownV2 (жирный, кликабельные ссылки).

## Переменные окружения

- `BOT_TOKEN` — токен бота.
- `WEBHOOK_SECRET` — секрет для заголовка `X-Telegram-Bot-Api-Secret-Token`.
- `BASE_URL` — публичный URL сервиса на Render, например `https://<service>.onrender.com` (нужно для установки webhook).

## Запуск локально

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
set PORT=8000  # или export PORT=8000 в Linux/macOS
uvicorn app.main:app --host 0.0.0.0 --port %PORT%
```

Проверить, что сервис жив: `curl http://localhost:8000/healthz`.

## Деплой на Render (Web Service)

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Убедитесь, что заданы `BOT_TOKEN`, `WEBHOOK_SECRET`, `BASE_URL`.

## Установка webhook

После того как Render выдаст URL (`BASE_URL`), выполните:

```bash
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" ^
  -H "Content-Type: application/json" ^
  -d "{\"url\": \"${BASE_URL}/telegram/webhook\", \"secret_token\": \"${WEBHOOK_SECRET}\"}"
```

Проверка текущего состояния webhook:

```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

## Формат сообщений

- Бот отправляет сообщения с `parse_mode=MarkdownV2` в тот же чат, откуда получил текст.
- Спецсимволы автоматически экранируются, голые ссылки превращаются в кликабельные.
- Запись вида `**текст**` конвертируется в жирный шрифт.
