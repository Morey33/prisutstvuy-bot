import logging
from telegram.ext import Application
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db import get_all_users_for_schedule
from practices import get_practice

logger = logging.getLogger(__name__)

def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        send_morning_messages,
        CronTrigger(hour=8, minute=0),
        args=[app],
        id="morning"
    )
    scheduler.add_job(
        send_evening_messages,
        CronTrigger(hour=21, minute=0),
        args=[app],
        id="evening"
    )

    scheduler.start()
    logger.info("Планировщик запущен")
    return scheduler


async def send_morning_messages(app: Application):
    users = get_all_users_for_schedule()
    for user in users:
        try:
            await app.bot.send_message(
                chat_id=user["telegram_id"],
                text="Доброе утро.\n\nОдним словом — как ты?"
            )
        except Exception as e:
            logger.warning(f"Не смог отправить утреннее {user['telegram_id']}: {e}")


async def send_evening_messages(app: Application):
    users = get_all_users_for_schedule()
    for user in users:
        try:
            await app.bot.send_message(
                chat_id=user["telegram_id"],
                text="Вечер.\n\nГде сегодня ты был по-настоящему здесь?"
            )
        except Exception as e:
            logger.warning(f"Не смог отправить вечернее {user['telegram_id']}: {e}")
