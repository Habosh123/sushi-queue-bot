from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from vkbottle.bot import Message

bot_cmids_by_peer: dict[int, list[int]] = {}
bot_message_ids_by_peer: dict[int, list[int]] = {}

BUTTON_TEXTS_TO_CLEAN = {
    "▶️ Начать",
    "Начать",
    "начать",
    "/start",
    "start",
    "🔀 Выбор режима",
    "🛡 Админ-панель",
    "🚚 Меню курьера",
    "🚀 Вызвать",
    "📋 Очередь",
    "👥 Управление курьерами",
    "🔄 Обновить",
    "🧹 Очистить очередь",
    "➕ Добавить курьера",
    "➖ Удалить курьера",
    "📋 Список всех курьеров",
    "⬅️ Назад",
    "✅ Да, очистить",
    "❌ Нет, отмена",
    "🚚 Занять очередь",
    "❌ Покинуть очередь",
    "❌ Выйти из очереди",
    "✅ Да, покинуть",
    "❌ Нет, остаться",
}


def _as_int_list(value: Any) -> list[int]:
    if value is None or isinstance(value, bool):
        return []

    if isinstance(value, int):
        return [value]

    if isinstance(value, str) and value.isdigit():
        return [int(value)]

    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        result: list[int] = []
        for item in value:
            result.extend(_as_int_list(item))
        return result

    return []


def _get_value(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)

        if value is not None:
            return value

    return None


def _get_cmid(obj: Any) -> int | None:
    value = _get_value(obj, "conversation_message_id", "cmid")
    return value if isinstance(value, int) else None


def _get_message_id(obj: Any) -> int | None:
    value = _get_value(obj, "message_id", "id")
    return value if isinstance(value, int) else None


def _get_text(obj: Any) -> str:
    value = _get_value(obj, "text")
    return value if isinstance(value, str) else ""


def _get_out(obj: Any) -> bool:
    value = _get_value(obj, "out")
    return bool(value) if value is not None else False


def _get_message_ids(sent_response: Any) -> list[int]:
    ids = _as_int_list(sent_response)

    if ids:
        return ids

    if isinstance(sent_response, dict):
        for key in ("message_id", "message_ids", "response"):
            ids.extend(_as_int_list(sent_response.get(key)))

    for attr in ("message_id", "message_ids", "response"):
        ids.extend(_as_int_list(getattr(sent_response, attr, None)))

    return ids


async def delete_cmids(message: Message, cmids: list[int]) -> None:
    cmids = sorted(set(cmids))

    if not cmids:
        return

    try:
        await message.ctx_api.messages.delete(
            peer_id=message.peer_id,
            cmids=cmids,
            delete_for_all=True,
        )
    except Exception:
        pass


async def delete_message_ids(message: Message, message_ids: list[int]) -> None:
    message_ids = sorted(set(message_ids))

    if not message_ids:
        return

    try:
        await message.ctx_api.messages.delete(
            message_ids=message_ids,
            delete_for_all=True,
        )
    except Exception:
        pass


async def delete_previous_bot_messages(message: Message) -> None:
    peer_id = message.peer_id

    cmids = bot_cmids_by_peer.pop(peer_id, [])
    message_ids = bot_message_ids_by_peer.pop(peer_id, [])

    await delete_cmids(message, cmids)
    await delete_message_ids(message, message_ids)


async def delete_trigger_message(message: Message) -> None:
    cmids: list[int] = []
    message_ids: list[int] = []

    cmid = _get_cmid(message)
    if cmid:
        cmids.append(cmid)

    message_id = _get_message_id(message)
    if message_id:
        message_ids.append(message_id)

    await delete_cmids(message, cmids)
    await delete_message_ids(message, message_ids)


async def delete_recent_noise(message: Message, count: int = 20) -> None:
    """
    Чистит старые кнопочные сообщения и предыдущие ответы бота.
    Это нужно после перезапуска, когда in-memory список прошлых сообщений уже потерян.
    """
    try:
        history = await message.ctx_api.messages.get_history(
            peer_id=message.peer_id,
            count=count,
        )
    except Exception:
        return

    items = getattr(history, "items", None)

    if items is None and isinstance(history, dict):
        items = history.get("items")

    if not items:
        return

    cmids: list[int] = []
    message_ids: list[int] = []

    for item in items:
        text = _get_text(item).strip()
        is_old_bot_message = _get_out(item)
        is_button_message = text in BUTTON_TEXTS_TO_CLEAN

        if not is_old_bot_message and not is_button_message:
            continue

        cmid = _get_cmid(item)
        if cmid:
            cmids.append(cmid)

        message_id = _get_message_id(item)
        if message_id:
            message_ids.append(message_id)

    await delete_cmids(message, cmids)
    await delete_message_ids(message, message_ids)


async def remember_bot_message(message: Message, sent_response: Any) -> None:
    peer_id = message.peer_id

    cmid = _get_cmid(sent_response)
    if cmid:
        bot_cmids_by_peer.setdefault(peer_id, []).append(cmid)

    message_ids = _get_message_ids(sent_response)
    if message_ids:
        bot_message_ids_by_peer.setdefault(peer_id, []).extend(message_ids)


async def clean_answer(
    message: Message,
    text: str,
    keyboard: str | None = None,
    *,
    delete_previous: bool = True,
    delete_trigger: bool = True,
):
    if delete_previous:
        await delete_previous_bot_messages(message)
        await delete_recent_noise(message)

    if delete_trigger:
        await delete_trigger_message(message)

    sent_response = await message.answer(
        text,
        keyboard=keyboard,
    )

    await remember_bot_message(message, sent_response)

    return sent_response
