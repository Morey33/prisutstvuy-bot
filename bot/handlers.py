import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    ConversationHandler, filters
)
from db import upsert_user, get_user, add_checkin, add_evening_note, save_gift_story, touch_last_active
from ai import classify_state
from practices import get_practice, STATE_LABELS

logger = logging.getLogger(__name__)

ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# Состояния ConversationHandler
GIFT_NAME, GIFT_WHY, GIFT_WANT = range(3)
EVENING_NOTE = 10

# Кнопки главного меню
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("Как я сейчас"), KeyboardButton("Утреннее намерение")],
        [KeyboardButton("Вечерняя пауза"), KeyboardButton("Практика")],
        [KeyboardButton("Получить подписку"), KeyboardButton("Настройки")],
    ], resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username or "", user.first_name or "")

    await update.message.reply_text(
        f"Привет{', ' + user.first_name if user.first_name else ''}.\n\n"
        "Я — Присутствуй.\n\n"
        "Не коуч, не дневник, не таймер.\n"
        "Просто тихое место, куда можно зайти когда голова слишком шумит — "
        "или когда хочется побыть чуть внимательнее к себе.\n\n"
        "Скажи — как ты прямо сейчас? Напиши своими словами или выбери внизу.",
        reply_markup=main_menu()
    )


async def handle_state_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик — принимает любой текст и определяет состояние."""
    user = update.effective_user
    text = update.message.text.strip()
    touch_last_active(user.id)

    # Специальные кнопки меню
    if text == "Утреннее намерение":
        practice = get_practice("morning")
        await update.message.reply_text(practice, reply_markup=main_menu())
        add_checkin(user.id, "morning", "утро", source="menu")
        return

    if text == "Вечерняя пауза":
        await update.message.reply_text(
            "Один вопрос на сегодня:\n\n"
            "Где ты был по-настоящему здесь?\n\n"
            "Напиши — один момент, одно слово, образ. Всё подойдёт.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data["awaiting_evening"] = True
        return

    if text == "Практика":
        last = context.user_data.get("last_state", "anxiety")
        practice = get_practice(last)
        await update.message.reply_text(practice, reply_markup=main_menu())
        return

    if text == "Настройки":
        await update.message.reply_text(
            "Настройки пока в разработке.\n\n"
            "Напиши мне напрямую если хочешь изменить время напоминаний.",
            reply_markup=main_menu()
        )
        return

    # Если ждём вечернюю заметку
    if context.user_data.get("awaiting_evening"):
        add_evening_note(user.id, text)
        context.user_data["awaiting_evening"] = False
        await update.message.reply_text(
            "Спасибо. Это важно — просто заметить.\n\n"
            "Завтра — чистый лист.",
            reply_markup=main_menu()
        )
        return

    # Классификация свободного текста через ИИ
    state, word = await classify_state(text)
    context.user_data["last_state"] = state
    add_checkin(user.id, state, word)

    practice = get_practice(state)
    label = STATE_LABELS.get(state, "")

    response = f"Слышу — {word}.\n\n{practice}"
    await update.message.reply_text(response, reply_markup=main_menu())


# ── Gift flow ──────────────────────────────────────────────

async def gift_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = get_user(update.effective_user.id)
    if db_user and db_user["subscription"] in ("gift", "paid"):
        await update.message.reply_text(
            "У тебя уже есть полный доступ. Спасибо что ты здесь.",
            reply_markup=main_menu()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Хочешь получить полный доступ бесплатно?\n\n"
        "Я читаю заявки сам — не алгоритм.\n\n"
        "Первый вопрос: как тебя зовут?",
        reply_markup=ReplyKeyboardRemove()
    )
    return GIFT_NAME


async def gift_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["gift_name"] = update.message.text.strip()
    await update.message.reply_text(
        "Что привело тебя сюда?\n\n"
        "Нет правильного ответа — пиши как пишется."
    )
    return GIFT_WHY


async def gift_why(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["gift_why"] = update.message.text.strip()
    await update.message.reply_text(
        "Последний вопрос:\n\n"
        "Что ты хочешь заметить или изменить в своей жизни?"
    )
    return GIFT_WANT


async def gift_want(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = context.user_data.get("gift_name", "—")
    why = context.user_data.get("gift_why", "—")
    want = update.message.text.strip()

    story = f"Имя: {name}\nПочему: {why}\nЧто хочет: {want}"
    save_gift_story(user.id, story)

    await update.message.reply_text(
        "Спасибо, что написал. Я прочитаю и напишу тебе.",
        reply_markup=main_menu()
    )

    # Отправляем тебе как админу
    if ADMIN_ID:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📩 Новая заявка на gift-подписку\n\n"
                f"👤 @{user.username or 'нет'} (id: {user.id})\n\n"
                f"Имя: {name}\n"
                f"Почему: {why}\n"
                f"Что хочет: {want}\n\n"
                f"Чтобы открыть доступ: /grant {user.id}"
            )
        )
    return ConversationHandler.END


async def grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для тебя — /grant <telegram_id>"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Использование: /grant <telegram_id>")
        return

    target_id = int(context.args[0])
    from db import set_subscription
    set_subscription(target_id, "gift")

    await update.message.reply_text(f"✅ Подписка gift открыта для {target_id}")
    await context.bot.send_message(
        chat_id=target_id,
        text=(
            "Твой доступ открыт.\n\n"
            "Просто начни — никаких обязательств."
        )
    )


async def gift_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Окей, всегда можно вернуться.", reply_markup=main_menu())
    return ConversationHandler.END


# ── Сборка хендлеров ───────────────────────────────────────

def build_handlers():
    gift_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Получить подписку$"), gift_start),
            CommandHandler("gift", gift_start),
        ],
        states={
            GIFT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_name)],
            GIFT_WHY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_why)],
            GIFT_WANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_want)],
        },
        fallbacks=[CommandHandler("cancel", gift_cancel)],
    )

    return [
        CommandHandler("start", start),
        CommandHandler("grant", grant),
        gift_conv,
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_state_input),
    ]
