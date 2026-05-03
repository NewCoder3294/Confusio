"""Run the defensive Telegram bot.

  TELEGRAM_API_ID=... TELEGRAM_API_HASH=... TELEGRAM_BOT_TOKEN=... \
      python -m defensive.bot
"""
import asyncio

from defensive.bot.telegram import run

if __name__ == "__main__":
    asyncio.run(run())
