import os
import logging
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import setup_application

import db

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
WEBAPP_PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


class AskStates(StatesGroup):
    waiting_for_question = State()
    waiting_for_answer = State()


def get_ask_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ask_{user_id}"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""

    await db.register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    if args.startswith("ask_"):
        target_id = int(args[4:])
        target = await db.get_user(target_id)
        if not target:
            await message.answer("Пользователь не найден.")
            return
        target_name = target["first_name"] or target["username"] or "Пользователь"
        await state.set_state(AskStates.waiting_for_question)
        await state.update_data(target_id=target_id)
        await message.answer(
            f"📝 Задай анонимный вопрос для {target_name}:\n\n"
            "Просто напиши его ниже. Твоё имя не будет показано."
        )
    else:
        link = get_ask_link(message.from_user.id)
        await message.answer(
            f"👋 Привет! Это бот для анонимных вопросов.\n\n"
            f"📌 Твоя ссылка для вопросов:\n{link}\n\n"
            f"Вставь её в био Telegram — и любой сможет задать тебе анонимный вопрос!\n\n"
            f"Команды:\n"
            f"/myquestions — посмотреть неотвеченные вопросы\n"
            f"/link — получить свою ссылку ещё раз"
        )


@router.message(Command("link"))
async def cmd_link(message: Message):
    await db.register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    link = get_ask_link(message.from_user.id)
    await message.answer(f"📌 Твоя ссылка для анонимных вопросов:\n{link}")


@router.message(AskStates.waiting_for_question)
async def process_question(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        return

    data = await state.get_data()
    target_id = data.get("target_id")
    if not target_id:
        await state.clear()
        await message.answer("Ошибка. Попробуй перейти по ссылке ещё раз.")
        return

    q_id = await db.save_question(target_id, message.from_user.id, message.text)

    await state.clear()
    await message.answer("✅ Вопрос отправлен анонимно!")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"answer_{q_id}")]
    ])
    await bot.send_message(
        target_id,
        f"📬 Новый анонимный вопрос:\n\n❓ {message.text}",
        reply_markup=kb,
    )


@router.message(Command("myquestions"))
async def cmd_myquestions(message: Message):
    questions = await db.get_unanswered_questions(message.from_user.id)
    if not questions:
        await message.answer("У тебя нет неотвеченных вопросов 🎉")
        return

    for q in questions[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"answer_{q['id']}")]
        ])
        await message.answer(
            f"❓ {q['text']}\n\n🕐 {q['created_at']}",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("answer_"))
async def callback_answer(callback: CallbackQuery, state: FSMContext):
    q_id = int(callback.data[7:])
    question = await db.get_question_by_id(q_id)
    if not question:
        await callback.answer("Вопрос не найден.")
        return

    await state.set_state(AskStates.waiting_for_answer)
    await state.update_data(question_id=q_id, sender_id=question["sender_user_id"])
    await callback.message.answer(
        f"💬 Напиши ответ на вопрос:\n\n❓ {question['text']}"
    )
    await callback.answer()


@router.message(AskStates.waiting_for_answer)
async def process_answer(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        return

    data = await state.get_data()
    q_id = data.get("question_id")
    sender_id = data.get("sender_id")
    if not q_id:
        await state.clear()
        await message.answer("Ошибка. Попробуй ещё раз.")
        return

    await db.save_answer(q_id, message.text)
    await state.clear()
    await message.answer("✅ Ответ сохранён!")

    if sender_id:
        try:
            question = await db.get_question_by_id(q_id)
            q_text = question["text"] if question else "(вопрос не найден)"
            await bot.send_message(
                sender_id,
                f"📬 Тебе пришел ответ на анонимный вопрос:\n\n❓ {q_text}\n💬 {message.text}",
            )
        except Exception:
            pass


async def on_startup(bot: Bot):
    await db.init_db()
    if not BOT_USERNAME:
        me = await bot.me()
        os.environ["BOT_USERNAME"] = me.username
        globals()["BOT_USERNAME"] = me.username
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to {WEBHOOK_URL}")
    else:
        logger.warning("WEBHOOK_HOST not set, webhook not configured")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    await bot.session.close()


def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    setup_application(app, dp, bot=bot, path=WEBHOOK_PATH)

    # Health check endpoint for Render
    async def health_check(request):
        return web.Response(text="ok")

    app.router.add_get("/", health_check)

    web.run_app(app, host="0.0.0.0", port=WEBAPP_PORT)


if __name__ == "__main__":
    main()
