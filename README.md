# Anon Questions Bot

Бот для анонимных вопросов в Telegram.

## Как работает

1. Пользователь пишет `/start` → получает уникальную ссылку вида `https://t.me/YourBot?start=ask_12345`
2. Вставляет ссылку в био Telegram
3. Кто-то кликает по ссылке → открывается чат с ботом → бот просит написать вопрос
4. Вопрос приходит пользователю анонимно
5. Пользователь может ответить на вопрос — ответ придёт отправителю

## Команды

- `/start` — регистрация + получение ссылки
- `/link` — получить свою ссылку ещё раз
- `/myquestions` — список неотвеченных вопросов

## Настройка PostgreSQL (Neon — бесплатно)

1. Зарегистрируйся на [neon.tech](https://neon.tech) (через GitHub, без карты)
2. Создай новый проект → получи строку подключения вида `postgresql://user:pass@ep-xxx.neon.tech/dbname`
3. Это и есть `DATABASE_URL`

## Запуск локально

```bash
pip install -r requirements.txt
cp .env.example .env  # заполни BOT_TOKEN, BOT_USERNAME, DATABASE_URL
python run_bot.py
```

Бот запустит веб-сервер на порту 10000. Для локальной тестировки можно переключить на polling (убрать WEBHOOK_HOST).

## Деплой на Render

1. Создай репозиторий на GitHub, запушь код
2. На [render.com](https://render.com) → New → Web Service → выбери репо
3. Render подхватит `render.yaml` автоматически
4. Добавь env vars:
   - `BOT_TOKEN` — токен от @BotFather
   - `BOT_USERNAME` — юзернейм бота (без @)
   - `DATABASE_URL` — строка подключения Neon PostgreSQL
5. Render автоматически подставит `RENDER_EXTERNAL_HOSTNAME` и `PORT`

**Почему web-сервис, а не worker?** Web-сервис на free tier просыпается по HTTP-запросу — Telegram webhook разбудит бота при новом сообщении. Worker не просыпается автоматически.

## Монетизация (идеи на будущее)

- Премиум: видеть кто задал вопрос
- Кастомные темы/стили вопросов
- Лимит бесплатных вопросов, безлимит за подписку
- Рекламные сообщения
