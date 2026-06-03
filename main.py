"""
Classroom Companion — Entry Point
Runs the Telegram bot and FastAPI web server concurrently.
"""
import asyncio
import logging
import threading
import uvicorn
from telegram.ext import Application
from db.models import init_db
from bot.handlers import get_handlers
from scheduler.reminders import start_scheduler
from api.routes import app as web_app
import config

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def run_web_server():
    uvicorn.run(
        web_app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="warning",
    )


async def run_bot():
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    for handler in get_handlers():
        application.add_handler(handler)

    # Register bot instance for web layer
    from bot.bot_instance import set_bot
    set_bot(application.bot)

    # Start reminder scheduler
    scheduler = start_scheduler(application.bot)

    logger.info("Starting Telegram bot...")
    async with application:
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running. Press Ctrl+C to stop.")

        try:
            await asyncio.Event().wait()  # Run until interrupted
        finally:
            scheduler.shutdown(wait=False)
            await application.updater.stop()
            await application.stop()


def main():
    # Initialize database
    init_db()
    logger.info("Database initialised.")

    # Start web server in a background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info(f"Web UI running at http://{config.WEB_HOST}:{config.WEB_PORT}")

    # Run bot in the main async loop
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
