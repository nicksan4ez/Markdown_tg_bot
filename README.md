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

## Локальное тестирование перед деплоем

1. Подготовить переменные в `.env`: скопируйте `.env.example` → `.env` и впишите реальные `BOT_TOKEN`, `WEBHOOK_SECRET`, `BASE_URL` (для локального теста можно поставить URL ngrok, см. ниже). Файл `.env` уже в `.gitignore`.
2. Активировать окружение и зависимости:  
   Bash/WSL: `source .venv/bin/activate && pip install -r requirements.txt`  
   PowerShell: `.\\.venv\\Scripts\\Activate.ps1; pip install -r requirements.txt`
3. Запустить сервер локально (переменные подтянутся из `.env` автоматически):  
   Bash/WSL: `PORT=8000 uvicorn app.main:app --host 0.0.0.0 --port $PORT`  
   PowerShell: `$env:PORT=8000; uvicorn app.main:app --host 0.0.0.0 --port $env:PORT`
4. Быстрый самотест без Telegram: отправьте мок-апдейт в вебхук с вашим `WEBHOOK_SECRET` и любым chat_id (бот всё равно берёт chat_id из апдейта и отвечает туда же):  
   `curl -X POST http://localhost:8000/telegram/webhook -H "Content-Type: application/json" -H "X-Telegram-Bot-Api-Secret-Token: $WEBHOOK_SECRET" -d "{\"message\":{\"chat\":{\"id\":123},\"text\":\"# Title\\n## Subtitle\\nText https://example.com **bold**\"}}"`
   Тут `id:123` — произвольный тестовый; главное проверить, что сервер отвечает 200 OK и форматирует текст.
5. Тест через Telegram до деплоя (ngrok):  
   - Запустить туннель: `ngrok http 8000` → взять `https://<subdomain>.ngrok.io`.  
   - Обновить `BASE_URL` в `.env` на этот адрес (без хвоста `/telegram/webhook`).  
   - Применить вебхук: `set -a; source .env; set +a; bash set_webhook.sh` (или задайте переменные вручную в PowerShell и запустите `bash set_webhook.sh`).  
   - Напишите боту — он ответит тем же текстом с форматированием.
6. Остановить: Ctrl+C в окне uvicorn / ngrok. Перед деплоем на Render верните `BASE_URL` к боевому домену.

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
- Строки, начинающиеся с `# ` → жирный+подчёркнутый заголовок с новой строки; с `## ` → жирный заголовок.
- Спецсимволы автоматически экранируются, голые ссылки превращаются в кликабельные.
- Запись вида `**текст**` конвертируется в жирный шрифт.
