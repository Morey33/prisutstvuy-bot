import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    ConversationHandler, filters
)
from db import upsert_user, get_user, add_checkin, add_evening_note, save_gift_story, touch_last_active, get_onboarding_day, advance_onboarding
from ai import classify_state
from practices import get_practice, STATE_LABELS
from onboarding import get_onboarding_morning, get_onboarding_evening, is_onboarding_complete

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
GIFT_NAME, GIFT_WHY, GIFT_WANT = range(3)
MENU_BUTTONS = {"Утреннее намерение", "Вечерняя пауза", "Получить подписку", "Настройки"}

def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("Утреннее намерение"), KeyboardButton("Вечерняя пауза")],
        [KeyboardButton("Получить подписку"), KeyboardButton("Настройки")],
    ], resize_keyboard=True)

async def start(update, context):
    user = update.effective_user
    upsert_user(user.id, user.username or "", user.first_name or "")
    context.user_data.clear()
    day = get_onboarding_day(user.id)
    morning = get_onboarding_morning(day)
    if morning:
        await update.message.reply_text(f"Привет{', ' + user.first_name if user.first_name else ''}.\n\nЯ — Присутствуй.\n\nНе коуч, не дневник, не таймер.\nПросто тихое место, куда можно зайти когда голова слишком шумит.\n\nБуду рядом 7 дней — каждый день одна маленькая практика.\nПотом ты сам решаешь как пользоваться.\n\nНачнём?", reply_markup=main_menu())
        await update.message.reply_text(morning)
    else:
        await update.message.reply_text(f"С возвращением{', ' + user.first_name if user.first_name else ''}.\n\nКак ты? Напиши — я слушаю.", reply_markup=main_menu())

async def handle_state_input(update, context):
    user = update.effective_user
    text = update.message.text.strip()
    touch_last_active(user.id)

    if text == "Утреннее намерение":
        day = get_onboarding_day(user.id)
        morning = get_onboarding_morning(day)
        if morning and not is_onboarding_complete(day):
            await update.message.reply_text(morning, reply_markup=main_menu())
        else:
            await update.message.reply_text(get_practice("morning"), reply_markup=main_menu())
            add_checkin(user.id, "morning", "утро", source="menu")
        return

    if text == "Вечерняя пауза":
        day = get_onboarding_day(user.id)
        evening = get_onboarding_evening(day)
        if evening and not is_onboarding_complete(day):
            await update.message.reply_text(evening, reply_markup=main_menu())
            advance_onboarding(user.id)
        else:
            await update.message.reply_text("Один вопрос на сегодня:\n\nГде ты был по-настоящему здесь?\n\nНапиши — один момент, одно слово, образ.", reply_markup=ReplyKeyboardRemove())
            context.user_data["awaiting_evening"] = True
        return

    if text == "Настройки":
        await update.message.reply_text("Настройки пока в разработке.\n\nНапиши мне напрямую если хочешь изменить время напоминаний.", reply_markup=main_menu())
        return

    if context.user_data.get("awaiting_evening"):
        add_evening_note(user.id, text)
        context.user_data["awaiting_evening"] = False
        await update.message.reply_text("Спасибо. Это важно — просто заметить.\n\nЗавтра — чистый лист.", reply_markup=main_menu())
        return

    if text not in MENU_BUTTONS:
        state, word = await classify_state(text)
        context.user_data["last_state"] = state
        if word in ("состояние", "state", ""):
            word = STATE_LABELS.get(state, "это")
        add_checkin(user.id, state, word)
        practice = get_practice(state, exclude=context.user_data.get("last_practice"))
        context.user_data["last_practice"] = practice
        await update.message.reply_text(f"Слышу — {word}.\n\n{practice}", reply_markup=main_menu())

async def gift_start(update, context):
    db_user = get_user(update.effective_user.id)
    if db_user and db_user["subscription"] in ("gift", "paid"):
        await update.message.reply_text("У тебя уже есть полный доступ. Спасибо что ты здесь.", reply_markup=main_menu())
        return ConversationHandler.END
    await update.message.reply_text("Хочешь получить полный доступ бесплатно?\n\nЯ читаю заявки сам — не алгоритм.\n\nПервый вопрос: как тебя зовут?", reply_markup=ReplyKeyboardRemove())
    return GIFT_NAME

async def gift_name(update, context):
    context.user_data["gift_name"] = update.message.text.strip()
    await update.message.reply_text("Что привело тебя сюда?\n\nНет правильного ответа — пиши как пишется.")
    return GIFT_WHY

async def gift_why(update, context):
    context.user_data["gift_why"] = update.message.text.strip()
    await update.message.reply_text("Последний вопрос:\n\nЧто ты хочешь заметить или изменить в своей жизни?")
    return GIFT_WANT

async def gift_want(update, context):
    user = update.effective_user
    name = context.user_data.get("gift_name", "—")
    why = context.user_data.get("gift_why", "—")
    want = update.message.text.strip()
    save_gift_story(user.id, f"Имя: {name}\nПочему: {why}\nЧто хочет: {want}")
    await update.message.reply_text("Спасибо, что написал. Я прочитаю и напишу тебе.", reply_markup=main_menu())
    if ADMIN_ID:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 Новая заявка\n\n👤 @{user.username or 'нет'} (id: {user.id})\n\nИмя: {name}\nПочему: {why}\nЧто хочет: {want}\n\nОткрыть: /grant {user.id}")
    return ConversationHandler.END

async def grant(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /grant <id>")
        return
    from db import set_subscription
    set_subscription(int(context.args[0]), "gift")
    await update.message.reply_text(f"✅ Открыто для {context.args[0]}")
    await context.bot.send_message(chat_id=int(context.args[0]), text="Твой доступ открыт.\n\nПросто начни — никаких обязательств.")

async def gift_cancel(update, context):
    await update.message.reply_text("Окей, всегда можно вернуться.", reply_markup=main_menu())
    return ConversationHandler.END

def build_handlers():
    gift_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Получить подписку$"), gift_start), CommandHandler("gift", gift_start)],
        states={GIFT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_name)], GIFT_WHY: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_why)], GIFT_WANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_want)]},
        fallbacks=[CommandHandler("cancel", gift_cancel)],
    )
    return [CommandHandler("start", start), CommandHandler("grant", grant), gift_conv, MessageHandler(filters.TEXT & ~filters.COMMAND, handle_state_input)]
