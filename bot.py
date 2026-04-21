import os
import logging
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Update, BotCommand,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

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


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Моя ссылка", callback_data="menu_link")],
        [
            InlineKeyboardButton(text="Вопросы", callback_data="menu_questions"),
            InlineKeyboardButton(text="Статистика", callback_data="menu_stats"),
        ],
        [InlineKeyboardButton(text="Помощь", callback_data="menu_help")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="cancel")]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""

    await db.register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    if args.startswith("ask_"):
        target_id = int(args[4:])
        target = await db.get_user(target_id)
        if not target:
            await message.answer("Пользователь не найден. Возможно, он ещё не запускал бота.")
            return
        target_name = target["first_name"] or target["username"] or "Пользователь"
        await state.set_state(AskStates.waiting_for_question)
        await state.update_data(target_id=target_id)
        await message.answer(
            f"Анонимный вопрос для <b>{target_name}</b>\n\n"
            f"Напиши свой вопрос ниже. Отправитель останется неизвестным.\n\n"
            f"<i>Твоё имя нигде не появится.</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
    else:
        link = get_ask_link(message.from_user.id)
        await message.answer(
            f"Привет, <b>{message.from_user.first_name}</b>!\n\n"
            f"Бот для анонимных вопросов. Поделись ссылкой — и тебе смогут "
            f"задавать вопросы анонимно.\n\n"
            f"<b>Твоя ссылка:</b>\n<blockquote>{link}</blockquote>\n"
            f"<b>Вставь в био так:</b>\n"
            f"<blockquote>Спроси меня: t.me/{BOT_USERNAME}?start=ask_{message.from_user.id}</blockquote>\n"
            f"<i>Нажми на ссылку выше, чтобы скопировать</i>",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )


@router.message(Command("link"))
async def cmd_link(message: Message):
    await db.register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    link = get_ask_link(message.from_user.id)
    await message.answer(
        f"<b>Твоя ссылка для анонимных вопросов:</b>\n\n"
        f"<blockquote>{link}</blockquote>\n"
        f"<b>Для био:</b>\n"
        f"<blockquote>Спроси меня: t.me/{BOT_USERNAME}?start=ask_{message.from_user.id}</blockquote>",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Как пользоваться ботом</b>\n\n"
        "<b>Получить ссылку</b> — /link\n"
        "Вставь её в био Telegram, чтобы люди могли задавать тебе анонимные вопросы\n\n"
        "<b>Мои вопросы</b> — /myquestions\n"
        "Показывает все неотвеченные вопросы\n\n"
        "<b>Статистика</b> — /stats\n"
        "Сколько вопросов получено и отвечено\n\n"
        "<b>Отмена</b> — нажми кнопку «Отмена»\n"
        "во время написания вопроса или ответа\n\n"
        "<b>Совет:</b> добавь в био текст вида:\n"
        "<blockquote>Спроси меня: t.me/{BOT_USERNAME}?start=ask_...</blockquote>",
        parse_mode="HTML",
    )


@router.message(Command("myquestions"))
async def cmd_myquestions(message: Message):
    questions = await db.get_unanswered_questions(message.from_user.id)
    if not questions:
        await message.answer("Нет неотвеченных вопросов.")
        return

    await message.answer(f"<b>Неотвеченные вопросы ({len(questions)}):</b>", parse_mode="HTML")
    for q in questions[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"answer_{q['id']}")]
        ])
        await message.answer(
            f"{q['text']}",
            reply_markup=kb,
        )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    total_q, answered_q, unanswered_q = await db.get_user_stats(message.from_user.id)
    await message.answer(
        f"<b>Твоя статистика</b>\n\n"
        f"Получено вопросов: <b>{total_q}</b>\n"
        f"Отвечено: <b>{answered_q}</b>\n"
        f"Ожидает ответа: <b>{unanswered_q}</b>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu_link")
async def callback_menu_link(callback: CallbackQuery):
    await db.register_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    link = get_ask_link(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>Твоя ссылка для анонимных вопросов:</b>\n\n"
        f"<blockquote>{link}</blockquote>\n"
        f"<b>Вставь в био так:</b>\n"
        f"<blockquote>Спроси меня: t.me/{BOT_USERNAME}?start=ask_{callback.from_user.id}</blockquote>\n"
        f"<i>Нажми на ссылку, чтобы скопировать</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="menu_back")]
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_questions")
async def callback_menu_questions(callback: CallbackQuery):
    questions = await db.get_unanswered_questions(callback.from_user.id)
    if not questions:
        text = "Нет неотвеченных вопросов."
    else:
        text = f"<b>Неотвеченные вопросы ({len(questions)}):</b>\n\n"
        for i, q in enumerate(questions[:10], 1):
            text += f"<b>{i}.</b> {q['text']}\n\n"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="menu_back")]
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_stats")
async def callback_menu_stats(callback: CallbackQuery):
    total_q, answered_q, unanswered_q = await db.get_user_stats(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>Твоя статистика</b>\n\n"
        f"Получено вопросов: <b>{total_q}</b>\n"
        f"Отвечено: <b>{answered_q}</b>\n"
        f"Ожидает ответа: <b>{unanswered_q}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="menu_back")]
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_help")
async def callback_menu_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Как пользоваться ботом</b>\n\n"
        "<b>Получить ссылку</b> — /link\n"
        "Вставь её в био Telegram\n\n"
        "<b>Мои вопросы</b> — /myquestions\n"
        "Показывает неотвеченные вопросы\n\n"
        "<b>Статистика</b> — /stats\n"
        "Сколько вопросов получено/отвечено\n\n"
        "<b>Отмена</b> — кнопка «Отмена»\n"
        "при написании вопроса или ответа\n\n"
        "<b>Совет:</b> добавь в био:\n"
        f"<blockquote>Спроси меня: t.me/{BOT_USERNAME}?start=ask_...</blockquote>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="menu_back")]
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_back")
async def callback_menu_back(callback: CallbackQuery):
    link = get_ask_link(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>GhostAnon</b> — анонимные вопросы\n\n"
        f"<b>Твоя ссылка:</b>\n<blockquote>{link}</blockquote>\n"
        f"<b>Вставь в био:</b>\n"
        f"<blockquote>Спроси меня: t.me/{BOT_USERNAME}?start=ask_{callback.from_user.id}</blockquote>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.", reply_markup=None)
    link = get_ask_link(callback.from_user.id)
    await callback.message.answer(
        f"<b>GhostAnon</b> — анонимные вопросы\n\n"
        f"<b>Твоя ссылка:</b>\n<blockquote>{link}</blockquote>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


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
    await message.answer(
        "Вопрос отправлен анонимно!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Задать ещё", callback_data=f"askmore_{target_id}")]
        ]),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data=f"answer_{q_id}")]
    ])
    await bot.send_message(
        target_id,
        f"<b>Новый анонимный вопрос:</b>\n\n<blockquote>{message.text}</blockquote>",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("askmore_"))
async def callback_ask_more(callback: CallbackQuery, state: FSMContext):
    target_id = int(callback.data[8:])
    target = await db.get_user(target_id)
    if not target:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    target_name = target["first_name"] or target["username"] or "Пользователь"
    await state.set_state(AskStates.waiting_for_question)
    await state.update_data(target_id=target_id)
    await callback.message.answer(
        f"Анонимный вопрос для <b>{target_name}</b>\n\n"
        f"Напиши свой вопрос ниже. Отправитель останется неизвестным.\n\n"
        f"<i>Твоё имя нигде не появится.</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("answer_"))
async def callback_answer(callback: CallbackQuery, state: FSMContext):
    q_id = int(callback.data[7:])
    question = await db.get_question_by_id(q_id)
    if not question:
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    await state.set_state(AskStates.waiting_for_answer)
    await state.update_data(question_id=q_id, sender_id=question["sender_user_id"])
    await callback.message.answer(
        f"<b>Напиши ответ на вопрос:</b>\n\n<blockquote>{question['text']}</blockquote>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
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
    await message.answer("Ответ отправлен!", reply_markup=main_menu_kb())

    if sender_id:
        try:
            question = await db.get_question_by_id(q_id)
            q_text = question["text"] if question else "..."
            ask_more_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Задать ещё", callback_data=f"askmore_{message.from_user.id}")]
            ])
            await bot.send_message(
                sender_id,
                f"<b>Ответ на твой анонимный вопрос:</b>\n\n<blockquote>{q_text}</blockquote>\n\n{message.text}",
                parse_mode="HTML",
                reply_markup=ask_more_kb,
            )
        except Exception:
            pass


async def on_startup(bot: Bot):
    print(f"[STARTUP] Initializing database...")
    await db.init_db()
    print(f"[STARTUP] Database initialized")

    if not BOT_USERNAME:
        me = await bot.me()
        os.environ["BOT_USERNAME"] = me.username
        globals()["BOT_USERNAME"] = me.username
    print(f"[STARTUP] Bot username: {BOT_USERNAME}")

    await bot.set_my_commands([
        BotCommand(command="link", description="Моя ссылка"),
        BotCommand(command="myquestions", description="Неотвеченные вопросы"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="help", description="Помощь"),
    ])
    print(f"[STARTUP] Bot commands set")

    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
        print(f"[STARTUP] Webhook set to {WEBHOOK_URL}")
    else:
        print(f"[STARTUP] WARNING: WEBHOOK_HOST not set, webhook not configured")
        print(f"[STARTUP] RENDER_EXTERNAL_HOSTNAME={os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'NOT SET')}")


async def on_shutdown(bot: Bot):
    await bot.session.close()


async def on_app_startup(app):
    print(f"[STARTUP] on_app_startup called")
    try:
        await on_startup(bot)
        print(f"[STARTUP] on_startup completed successfully")
    except Exception as e:
        print(f"[STARTUP] FAILED: {e}")
        import traceback
        traceback.print_exc()


async def on_app_shutdown(app):
    await on_shutdown(bot)


def main():
    app = web.Application()

    app.on_startup.append(on_app_startup)
    app.on_shutdown.append(on_app_shutdown)

    async def handle_webhook(request):
        try:
            data = await request.json()
            update = Update.model_validate(data, context={"bot": bot})
            await dp.feed_update(bot, update)
        except Exception as e:
            print(f"[WEBHOOK ERROR] {e}")
        return web.Response(text="ok")

    async def health_check(request):
        return web.Response(text="ok")

    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", health_check)

    print(f"[STARTUP] Starting on port {WEBAPP_PORT}, webhook_url={WEBHOOK_URL}")
    web.run_app(app, host="0.0.0.0", port=WEBAPP_PORT)


if __name__ == "__main__":
    main()
