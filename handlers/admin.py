from vkbottle.bot import BotLabeler, Message

from config.settings import ADMIN_IDS
from database.db import SessionLocal
from keyboards.keyboards import (
    admin_couriers_keyboard,
    admin_main_keyboard,
    clear_queue_confirm_keyboard,
    courier_ready_keyboard,
)
from services.message_cleanup import clean_answer, delete_trigger_message
from services.message_payload import get_action
from services.queue_service import QueueService

labeler = BotLabeler()

admin_states: dict[int, str] = {}

WAITING_ADD_COURIER = "waiting_add_courier"
WAITING_REMOVE_COURIER = "waiting_remove_courier"
CONFIRM_CLEAR_QUEUE = "confirm_clear_queue"

ID_REGEXP = r"^\d{5,12}$"


def is_admin(vk_id: int) -> bool:
    return vk_id in ADMIN_IDS


def is_admin_message(message: Message) -> bool:
    return is_admin(message.from_id)


def is_admin_waiting_id(message: Message) -> bool:
    return is_admin(message.from_id) and admin_states.get(message.from_id) in {
        WAITING_ADD_COURIER,
        WAITING_REMOVE_COURIER,
    }


def admin_action(expected_action: str, *fallback_texts: str):
    def _filter(message: Message) -> bool:
        if not is_admin(message.from_id):
            return False

        action = get_action(message)

        if action:
            # Защита от старых клавиатур: payload мог остаться старый,
            # а текст кнопки уже другой. Совпадать должны и action, и label.
            return action == expected_action and message.text in fallback_texts

        return message.text in fallback_texts

    return _filter


async def get_vk_name(message: Message) -> str:
    try:
        users = await message.ctx_api.users.get(user_ids=[message.from_id])
        if users:
            return f"{users[0].first_name} {users[0].last_name}"
    except Exception:
        pass

    return f"Администратор {message.from_id}"


async def show_admin_main_menu(message: Message) -> None:
    async with SessionLocal() as session:
        service = QueueService(session)
        queue_text = await service.get_queue_text()

    await clean_answer(
        message,
        queue_text,
        keyboard=admin_main_keyboard(),
    )


@labeler.message(func=admin_action("open_admin", "🛡 Админ-панель", "Админ", "админ"))
async def admin_start_handler(message: Message):
    admin_states.pop(message.from_id, None)
    await show_admin_main_menu(message)


@labeler.message(func=admin_action("admin_call", "🚀 Вызвать"))
async def call_next_handler(message: Message):
    admin_states.pop(message.from_id, None)
    admin_name = await get_vk_name(message)

    async with SessionLocal() as session:
        service = QueueService(session)
        result = await service.call_next_courier(
            admin_vk_id=message.from_id,
            admin_name=admin_name,
        )
        await session.commit()

    if not result:
        await clean_answer(
            message,
            "📭 Очередь пустая.\n\nНекого вызывать.",
            keyboard=admin_main_keyboard(),
        )
        return

    await message.ctx_api.messages.send(
        user_id=result.courier_vk_id,
        random_id=0,
        message="❗️❗️❗️ВАША ОЧЕРЕДЬ❗️❗️❗️",
        keyboard=courier_ready_keyboard(),
    )

    if result.next_vk_id:
        await message.ctx_api.messages.send(
            user_id=result.next_vk_id,
            random_id=0,
            message="🔔 Вы следующий в очереди. Будьте готовы к выезду.",
        )

    text = "✅ Курьер вызван\n\n" f"🚚 Отправлен: {result.courier_name}"

    if result.next_name:
        text += f"\n🔔 Следующий: {result.next_name}"
    else:
        text += "\n📭 Очередь пустая"

    await clean_answer(
        message,
        text,
        keyboard=admin_main_keyboard(),
    )


@labeler.message(func=admin_action("admin_queue", "📋 Очередь"))
async def admin_queue_handler(message: Message):
    admin_states.pop(message.from_id, None)

    async with SessionLocal() as session:
        service = QueueService(session)
        queue_text = await service.get_queue_text()

    await clean_answer(
        message,
        queue_text,
        keyboard=admin_main_keyboard(),
    )


@labeler.message(func=admin_action("admin_couriers", "👥 Управление курьерами"))
async def couriers_manage_handler(message: Message):
    admin_states.pop(message.from_id, None)

    await clean_answer(
        message,
        "👥 Управление курьерами\n\nВыберите действие:",
        keyboard=admin_couriers_keyboard(),
    )


@labeler.message(func=admin_action("admin_add_courier", "➕ Добавить курьера"))
async def add_courier_start_handler(message: Message):
    admin_states[message.from_id] = WAITING_ADD_COURIER

    await clean_answer(
        message,
        "➕ Добавление курьера\n\nВведите VK ID курьера:",
        keyboard=admin_couriers_keyboard(),
    )


@labeler.message(func=admin_action("admin_remove_courier", "➖ Удалить курьера"))
async def remove_courier_start_handler(message: Message):
    admin_states[message.from_id] = WAITING_REMOVE_COURIER

    await clean_answer(
        message,
        "➖ Удаление курьера\n\nВведите VK ID курьера:",
        keyboard=admin_couriers_keyboard(),
    )


@labeler.message(func=admin_action("admin_couriers_list", "📋 Список всех курьеров"))
async def couriers_list_handler(message: Message):
    admin_states.pop(message.from_id, None)

    async with SessionLocal() as session:
        service = QueueService(session)
        text = await service.get_couriers_text()

    await clean_answer(
        message,
        text,
        keyboard=admin_couriers_keyboard(),
    )


@labeler.message(func=admin_action("admin_back", "⬅️ Назад"))
async def back_to_admin_main_handler(message: Message):
    admin_states.pop(message.from_id, None)
    await show_admin_main_menu(message)


@labeler.message(func=admin_action("admin_refresh", "🔄 Обновить"))
async def admin_refresh_handler(message: Message):
    admin_states.pop(message.from_id, None)

    async with SessionLocal() as session:
        service = QueueService(session)
        queue_text = await service.get_queue_text()

    if "пустая" in queue_text.lower():
        if not getattr(message, "is_callback_context", False):
            await delete_trigger_message(message)
        return

    await clean_answer(
        message,
        queue_text,
        keyboard=admin_main_keyboard(),
    )


@labeler.message(func=admin_action("admin_clear_queue", "🧹 Очистить очередь"))
async def clear_queue_start_handler(message: Message):
    admin_states[message.from_id] = CONFIRM_CLEAR_QUEUE

    async with SessionLocal() as session:
        service = QueueService(session)
        queue_text = await service.get_queue_text()

    await clean_answer(
        message,
        "⚠️ Подтверждение очистки очереди\n\n"
        f"{queue_text}\n\n"
        "Вы точно хотите очистить очередь?",
        keyboard=clear_queue_confirm_keyboard(),
    )


@labeler.message(func=admin_action("admin_clear_cancel", "❌ Нет, отмена"))
async def clear_queue_cancel_handler(message: Message):
    admin_states.pop(message.from_id, None)

    await clean_answer(
        message,
        "✅ Действие отменено.",
        keyboard=admin_main_keyboard(),
    )


@labeler.message(func=admin_action("admin_clear_confirm", "✅ Да, очистить"))
async def clear_queue_confirm_handler(message: Message):
    if admin_states.get(message.from_id) != CONFIRM_CLEAR_QUEUE:
        await show_admin_main_menu(message)
        return

    async with SessionLocal() as session:
        service = QueueService(session)
        count = await service.clear_queue()
        await session.commit()

    admin_states.pop(message.from_id, None)

    await clean_answer(
        message,
        "🧹 Очередь очищена\n\n"
        f"Удалено из очереди: {count}",
        keyboard=admin_main_keyboard(),
    )


@labeler.message(regexp=ID_REGEXP, func=is_admin_waiting_id)
async def admin_add_or_remove_courier_handler(message: Message):
    state = admin_states.get(message.from_id)
    courier_vk_id = int(message.text.strip())

    async with SessionLocal() as session:
        service = QueueService(session)

        if state == WAITING_ADD_COURIER:
            user = await service.add_courier_by_vk_id(courier_vk_id)
            await session.commit()
            admin_states.pop(message.from_id, None)

            notification_text = ""

            try:
                await message.ctx_api.messages.send(
                    user_id=user.vk_id,
                    random_id=0,
                    message=(
                        "✅ Вас добавили в систему курьеров.\n\n"
                        "Нажмите «🚚 Занять очередь», когда приехали на точку."
                    ),
                    keyboard=courier_ready_keyboard(),
                )
            except Exception:
                notification_text = (
                    "\n\nℹ️ Бот не смог написать курьеру первым. "
                    "Пусть курьер сам откроет сообщения группы."
                )

            await clean_answer(
                message,
                "✅ Курьер добавлен\n\n"
                f"👤 {user.name}\n"
                f"ID: {user.vk_id}\n"
                "Статус: активен"
                f"{notification_text}",
                keyboard=admin_couriers_keyboard(),
            )
            return

        if state == WAITING_REMOVE_COURIER:
            removed = await service.remove_courier_by_vk_id(courier_vk_id)
            await session.commit()
            admin_states.pop(message.from_id, None)

            if removed:
                await clean_answer(
                    message,
                    "✅ Курьер удалён\n\n"
                    f"ID: {courier_vk_id}",
                    keyboard=admin_couriers_keyboard(),
                )
            else:
                await clean_answer(
                    message,
                    "⚠️ Курьер с таким ID не найден.",
                    keyboard=admin_couriers_keyboard(),
                )


@labeler.message(func=is_admin_waiting_id)
async def admin_invalid_id_handler(message: Message):
    await clean_answer(
        message,
        "⚠️ Некорректный VK ID.\n\nВведите только цифры.",
        keyboard=admin_couriers_keyboard(),
    )
