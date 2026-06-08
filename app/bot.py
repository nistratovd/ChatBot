import asyncio
import importlib
import importlib.util
import logging
import signal
from contextlib import suppress

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.config import get_settings
from app.database import create_pool
from app.keyboards import (
    RESTART_BUTTON_TEXT,
    question_keyboard,
    remove_restart_keyboard,
    restart_keyboard,
)
from app.models import AnswerOption, Question
from app.repository import QuizRepository, apply_schema
from app.security import escape_html_text

router = Router(name="quiz")
logger = logging.getLogger(__name__)

BOT_COMMANDS = [BotCommand(command="start", description="Перезапуск")]


@router.message(CommandStart())
async def start_quiz(message: Message, repo: QuizRepository) -> None:
    if message.from_user is None:
        return

    if not await ensure_quiz_access(message, repo):
        return

    attempt = await repo.get_or_create_active_attempt(message.from_user)
    if attempt is None:
        await message.answer_photo(
            photo="https://lassie.ru/upload/konkurs/images/ups.png?v",
            caption="Упс... Как говорил Джейсон Стетхем: «В одну и ту же реку нельзя войти дважды, а этот квиз можно пройти лишь однажды»",
            reply_markup=restart_keyboard(),
            protect_content=True,
        )
        return

    if attempt.total_questions == 0:
        await message.answer(
            "Опрос пока не содержит активных вопросов. Попробуйте позже.",
            reply_markup=restart_keyboard(),
            protect_content=True,
        )
        return

    await send_next_question(
        message,
        repo,
        attempt.id,
        intro_text="Опрос начался. Выберите один вариант ответа для каждого вопроса.",
    )


async def ensure_quiz_access(message: Message, repo: QuizRepository) -> bool:
    if message.from_user is None:
        return False

    if await repo.is_user_allowed(message.from_user.id):
        await repo.sync_allowed_user_profile(message.from_user)
        return True

    await message.answer(
        "Опрос доступен только участникам закрытого тестирования.",
        reply_markup=restart_keyboard(),
        protect_content=True,
    )
    return False


@router.message(Command("help"))
async def help_command(message: Message, repo: QuizRepository) -> None:
    await message.answer(
        "Команды:\n"
        "/start — начать или продолжить опрос\n"
        "/help — показать подсказку",
        reply_markup=await restart_keyboard_if_idle(message, repo),
        protect_content=True,
    )


@router.callback_query(F.data.startswith("answer:"))
async def process_answer(callback: CallbackQuery, repo: QuizRepository) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    try:
        _, question_id_raw, option_id_raw = callback.data.split(":", maxsplit=2)
        question_id = int(question_id_raw)
        option_id = int(option_id_raw)
    except ValueError:
        await callback.answer("Некорректный ответ", show_alert=True)
        return

    if not await repo.is_user_allowed(callback.from_user.id):
        await callback.answer(
            "Опрос доступен только участникам закрытого тестирования.",
            show_alert=True,
        )
        return
    await repo.sync_allowed_user_profile(callback.from_user)

    attempt = await repo.get_or_create_active_attempt(callback.from_user)
    if attempt is None:
        await callback.answer("Упс... Как говорил Джейсон Стетхем: «В одну и ту же реку нельзя войти дважды, а этот квиз можно пройти лишь однажды»", show_alert=True)
        return

    saved = await repo.save_answer(
        attempt_id=attempt.id,
        user=callback.from_user,
        question_id=question_id,
        option_id=option_id,
    )
    if saved is None:
        await callback.answer("Ответ уже сохранён или вопрос устарел", show_alert=True)
        return

    await callback.answer("Ответ сохранён")
    await remove_answered_question(callback.message)

    completed = await repo.complete_attempt_if_finished(attempt.id, callback.from_user)
    if completed:
        await callback.message.answer(
            "Ты ответил на все вопросы, молодчина! Подведём итоги совсем скоро. Следи за обновлениями в BetBoom Inside 😏",
            reply_markup=restart_keyboard(),
            protect_content=True,
        )
        return

    await send_next_question(callback.message, repo, attempt.id)


async def remove_answered_question(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        with suppress(TelegramBadRequest):
            await message.edit_reply_markup(reply_markup=None)


@router.message(F.text == RESTART_BUTTON_TEXT)
async def restart_button(message: Message, repo: QuizRepository) -> None:
    await start_quiz(message, repo)


@router.message()
async def fallback(message: Message, repo: QuizRepository) -> None:
    await message.answer(
        "Нажмите /start, чтобы начать или продолжить опрос.",
        reply_markup=await restart_keyboard_if_idle(message, repo),
        protect_content=True,
    )


async def restart_keyboard_if_idle(
    message: Message,
    repo: QuizRepository,
) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if message.from_user is None:
        return restart_keyboard()

    if await repo.is_user_voting(message.from_user.id):
        return remove_restart_keyboard()

    return restart_keyboard()


async def send_next_question(
    message: Message,
    repo: QuizRepository,
    attempt_id: int,
    intro_text: str | None = None,
) -> None:
    question = await repo.get_next_question(attempt_id)
    if question is None:
        await message.answer(
            "Ты ответил на все вопросы, молодчина! Подведём итоги совсем скоро. Следи за обновлениями в BetBoom Inside 😏",
            reply_markup=restart_keyboard(),
            protect_content=True,
        )
        return

    options = await repo.get_options(question.id)
    if not options:
        logger.warning("Question %s has no answer options", question.id)
        await message.answer(
            "Вопрос временно недоступен. Обратитесь к администратору.",
            reply_markup=remove_restart_keyboard(),
            protect_content=True,
        )
        return

    await _send_question(message, question, options, intro_text=intro_text)


async def _send_question(
    message: Message,
    question: Question,
    options: list[AnswerOption],
    intro_text: str | None = None,
) -> None:
    if question.display_number is None:
        text = escape_html_text(question.text)
    else:
        text = f"Вопрос {question.display_number}:\n{escape_html_text(question.text)}"

    if intro_text:
        text = f"{escape_html_text(intro_text)}\n\n{text}"

    keyboard = question_keyboard(options)
    photo = question.photo_file_id or question.photo_url
    if not photo:
        await message.answer(text, reply_markup=keyboard, protect_content=True)
        return

    try:
        await message.answer_photo(
            photo=photo,
            caption=text,
            reply_markup=keyboard,
            protect_content=True,
        )
    except TelegramBadRequest as exc:
        logger.warning(
            "Failed to send photo for question %s, falling back to text: %s",
            question.id,
            exc,
        )
        await message.answer(text, reply_markup=keyboard, protect_content=True)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    pool = await create_pool()
    await apply_schema(pool)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(repo=QuizRepository(pool))
    dispatcher.include_router(router)
    await bot.set_my_commands(BOT_COMMANDS)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    polling_task = asyncio.create_task(
        dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    )
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait({polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    if stop_task in done:
        polling_task.cancel()
    for task in pending:
        task.cancel()
    await bot.session.close()
    await pool.close()


if __name__ == "__main__":
    if importlib.util.find_spec("uvloop") is not None:
        importlib.import_module("uvloop").install()
    asyncio.run(main())
