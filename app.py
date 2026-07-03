import asyncio
import ssl

import aiohttp
from vkbottle import API
from vkbottle.bot import Bot
from vkbottle.http import AiohttpClient

from config.settings import VK_TOKEN, VK_VERIFY_SSL
from database.db import engine
from database.models import Base
from handlers.admin import labeler as admin_labeler
from handlers.courier import labeler as courier_labeler
from handlers.callbacks import register_callback_handlers


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main() -> None:
    ssl_context = None

    if not VK_VERIFY_SSL:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_context)
    )

    try:
        http_client = AiohttpClient(session=session)
        api = API(token=VK_TOKEN, http_client=http_client)
        bot = Bot(api=api)

        bot.labeler.load(admin_labeler)
        bot.labeler.load(courier_labeler)
        register_callback_handlers(bot)

        await create_tables()
        await bot.run_polling()
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
