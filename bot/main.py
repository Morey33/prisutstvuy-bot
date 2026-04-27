import os
import logging
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder

from db import init_db
from handlers import build_handlers
from scheduler import setup_scheduler

load_dotenv()
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)

def main():
    init_db()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN не задан в .env")

    app = ApplicationBuilder().token(token).build()

    for handler in build_handlers():
        app.add_handler(handler)

    setup_scheduler(app)

    logging.info("Бот запущен — @prisutstvuy_bot")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
