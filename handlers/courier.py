from vkbottle.bot import BotLabeler, Message

from config.settings import ADMIN_IDS
from database.db import SessionLocal
from keyboards.keyboards import (
    access_denied_keyboard,
    courier_in_queue_keyboard,
    courier_ready_keyboard,
    leave_queue_confirm_keyboard,
    role_select_keyboard,
)
from services.message_cleanup import clean_answer
from services.message_payload import get_action
from services.queue_service import QueueService

labeler = BotLabeler()

START_TEXTS = {"Начать", "начать", "▶️ Начать", "/start", "start"}
ROLE_SELECT_TEXTS = {"🔀 Выбор режима", "Выбор режима", "выбор режима"}


def is_admin(vk_id: int) -> bool:
    return vk_id in ADMIN_IDS


def access_denied_text(vk_id: int) -> str:
    return (
        "⛔ Доступ закрыт\n\n"
        "Вы пока не добавлены в систему курьеров.\n\n"
        "Ваш VK ID:\n"
        f"{vk_id}\n\n"
        "Скопируйте этот ID и отправьте администратору."
    )


def is_start_message(message: Message) -> bool:
    action = get_action(message)

    if action == "start":
        return True

    return message.text in START_TEXTS


def is_role_select_message(message: Message) -> bool:
    action = get_action(message)

    if action == "select_role":
        return True

    return message.text in ROLE_SELECT_TEXTS


def courier_action(expected_action: str, *fallback_texts: str):
    def _filter(message: Message) -> bool:
        action = get_action(message)

        if action:
            # Защита от старых клавиатур: payload мог остаться старый,
            # а текст кнопки уже другой. Совпадать должны и action, и label.
            return action == expected_action and message.text in fallback_texts

        if expected_action != "open_courier" and is_admin(message.from_id):
            return False

        return message.text in fallback_texts

    return _filter


async def get_vk_name(message: Message) -> str:
    try:
        users = await message.ctx_api.users.get(user_ids=[message.from_id])
        if users:
            return f"{users[0].first_name} {users[0].last_name}"
    except Exception:
        pass

    return f"Курьер {message.from_id}"


async def check_courier_access(message: Message) -> bool:
    async with SessionLocal() as session:
        service = QueueService(session)
        return await service.is_allowed_courier(message.from_id)


async def show_courier_menu(message: Message) -> None:
    allowed = await check_courier_access(message)

    if not allowed:
        await clean_answer(
            message,
            access_denied_text(message.from_id),
            keyboard=access_denied_keyboard(),
        )
        return

    async with SessionLocal() as session:
        service = QueueService(session)
        position = await service.get_position(message.from_id)
        queue_text = await service.get_queue_text()

    if position:
        await clean_answer(
            message,
            f"{queue_text}\n\n"
            f"📍 Ваш номер: {position.position} из {position.total}",
            keyboard=courier_in_queue_keyboard(),
        )
        return

    await clean_answer(
        message,
        "✅ Доступ подтверждён\n\n"
        "Нажмите «🚚 Занять очередь», когда приехали на точку.",
        keyboard=courier_ready_keyboard(),
    )


@labeler.message(func=is_role_select_message)
async def select_role_handler(message: Message):
    user_is_admin = is_admin(message.from_id)
    user_is_courier = await check_courier_access(message)

    if user_is_admin or user_is_courier:
        text = "Выберите режим работы:"

        if user_is_admin and not user_is_courier:
            text += (
                "\n\n"
                "Сейчас вы админ. Чтобы зайти как курьер, "
                "добавьте свой VK ID в список курьеров."
            )

        await clean_answer(
            message,
            text,
            keyboard=role_select_keyboard(),
        )
        return

    await clean_answer(
        message,
        access_denied_text(message.from_id),
        keyboard=access_denied_keyboard(),
    )


@labeler.message(func=is_start_message)
async def start_handler(message: Message):
    user_is_admin = is_admin(message.from_id)
    user_is_courier = await check_courier_access(message)

    if user_is_admin and user_is_courier:
        await clean_answer(
            message,
            "Выберите режим работы:",
            keyboard=role_select_keyboard(),
        )
        return

    if user_is_admin:
        from handlers.admin import show_admin_main_menu

        await show_admin_main_menu(message)
        return

    if user_is_courier:
        await show_courier_menu(message)
        return

    await clean_answer(
        message,
        access_denied_text(message.from_id),
        keyboard=access_denied_keyboard(),
    )


@labeler.message(func=courier_action("open_courier", "🚚 Меню курьера"))
async def open_courier_handler(message: Message):
    await show_courier_menu(message)


@labeler.message(func=courier_action("courier_join", "🚚 Занять очередь"))
async def join_queue_handler(message: Message):
    allowed = await check_courier_access(message)

    if not allowed:
        await clean_answer(
            message,
            access_denied_text(message.from_id),
            keyboard=access_denied_keyboard(),
        )
        return

    name = await get_vk_name(message)

    async with SessionLocal() as session:
        service = QueueService(session)

        try:
            position = await service.join_queue(
                vk_id=message.from_id,
                name=name,
            )
            queue_text = await service.get_queue_text()
            await session.commit()

        except PermissionError:
            await session.rollback()

            await clean_answer(
                message,
                "⛔ Вы заблокированы и не можете вставать в очередь.",
                keyboard=access_denied_keyboard(),
            )
            return

    await clean_answer(
        message,
        "✅ Вы заняли очередь.\n\n"
        f"{queue_text}\n\n"
        f"📍 Ваш номер: {position.position} из {position.total}",
        keyboard=courier_in_queue_keyboard(),
    )


@labeler.message(func=courier_action("courier_refresh", "🔄 Обновить", "📋 Очередь"))
async def queue_refresh_handler(message: Message):
    allowed = await check_courier_access(message)

    if not allowed:
        await clean_answer(
            message,
            access_denied_text(message.from_id),
            keyboard=access_denied_keyboard(),
        )
        return

    async with SessionLocal() as session:
        service = QueueService(session)
        position = await service.get_position(message.from_id)
        queue_text = await service.get_queue_text()

    if not position:
        await clean_answer(
            message,
            "Вы сейчас не стоите в очереди.\n\n"
            "Нажмите «🚚 Занять очередь», когда приехали на точку.",
            keyboard=courier_ready_keyboard(),
        )
        return

    await clean_answer(
        message,
        f"{queue_text}\n\n"
        f"📍 Ваш номер: {position.position} из {position.total}",
        keyboard=courier_in_queue_keyboard(),
    )


@labeler.message(func=courier_action("courier_leave_start", "❌ Покинуть очередь", "❌ Выйти из очереди"))
async def leave_queue_start_handler(message: Message):
    allowed = await check_courier_access(message)

    if not allowed:
        await clean_answer(
            message,
            access_denied_text(message.from_id),
            keyboard=access_denied_keyboard(),
        )
        return

    async with SessionLocal() as session:
        service = QueueService(session)
        position = await service.get_position(message.from_id)

    if not position:
        await clean_answer(
            message,
            "Вы сейчас не стоите в очереди.\n\n"
            "Нажмите «🚚 Занять очередь», когда приехали на точку.",
            keyboard=courier_ready_keyboard(),
        )
        return

    await clean_answer(
        message,
        "⚠️ Подтверждение выхода\n\n"
        "Вы точно хотите покинуть очередь?",
        keyboard=leave_queue_confirm_keyboard(),
    )


@labeler.message(func=courier_action("courier_leave_cancel", "❌ Нет, остаться"))
async def leave_queue_cancel_handler(message: Message):
    async with SessionLocal() as session:
        service = QueueService(session)
        position = await service.get_position(message.from_id)
        queue_text = await service.get_queue_text()

    if not position:
        await clean_answer(
            message,
            "Вы сейчас не стоите в очереди.\n\n"
            "Нажмите «🚚 Занять очередь», когда приехали на точку.",
            keyboard=courier_ready_keyboard(),
        )
        return

    await clean_answer(
        message,
        "✅ Вы остались в очереди.\n\n"
        f"{queue_text}\n\n"
        f"📍 Ваш номер: {position.position} из {position.total}",
        keyboard=courier_in_queue_keyboard(),
    )


@labeler.message(func=courier_action("courier_leave_confirm", "✅ Да, покинуть"))
async def leave_queue_confirm_handler(message: Message):
    async with SessionLocal() as session:
        service = QueueService(session)
        left = await service.leave_queue(message.from_id)

        if left:
            await session.commit()
        else:
            await session.rollback()

    if left:
        await clean_answer(
            message,
            "❌ Вы вышли из очереди.\n\n"
            "Нажмите «🚚 Занять очередь», когда снова будете готовы.",
            keyboard=courier_ready_keyboard(),
        )
    else:
        await clean_answer(
            message,
            "Вы не стояли в очереди.\n\n"
            "Нажмите «🚚 Занять очередь», когда приехали на точку.",
            keyboard=courier_ready_keyboard(),
        )
