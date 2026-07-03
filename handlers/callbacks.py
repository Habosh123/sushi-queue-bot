from __future__ import annotations

from typing import Any, Awaitable, Callable

from vkbottle import GroupEventType
from vkbottle.bot import Bot, MessageEvent

from handlers import admin, courier
from services.callback_context import CallbackMessageContext, get_callback_action

CallbackHandler = Callable[[CallbackMessageContext], Awaitable[None]]


ADMIN_ACTIONS: dict[str, CallbackHandler] = {
    "open_admin": admin.admin_start_handler,
    "admin_call": admin.call_next_handler,
    "admin_queue": admin.admin_queue_handler,
    "admin_couriers": admin.couriers_manage_handler,
    "admin_add_courier": admin.add_courier_start_handler,
    "admin_remove_courier": admin.remove_courier_start_handler,
    "admin_couriers_list": admin.couriers_list_handler,
    "admin_back": admin.back_to_admin_main_handler,
    "admin_refresh": admin.admin_refresh_handler,
    "admin_clear_queue": admin.clear_queue_start_handler,
    "admin_clear_cancel": admin.clear_queue_cancel_handler,
    "admin_clear_confirm": admin.clear_queue_confirm_handler,
}

COURIER_ACTIONS: dict[str, CallbackHandler] = {
    "open_courier": courier.open_courier_handler,
    "courier_join": courier.join_queue_handler,
    "courier_refresh": courier.queue_refresh_handler,
    "courier_leave_start": courier.leave_queue_start_handler,
    "courier_leave_cancel": courier.leave_queue_cancel_handler,
    "courier_leave_confirm": courier.leave_queue_confirm_handler,
}

START_ACTIONS = {"start"}
ROLE_SELECT_ACTIONS = {"select_role"}


def _event_value(event: Any, *names: str) -> Any:
    for name in names:
        value = getattr(event, name, None)
        if value is not None:
            return value

    obj = getattr(event, "object", None)

    if obj is not None:
        for name in names:
            value = getattr(obj, name, None)
            if value is not None:
                return value

            if isinstance(obj, dict):
                value = obj.get(name)
                if value is not None:
                    return value

    return None


async def _answer_callback(event: MessageEvent) -> None:
    """
    Закрывает индикатор загрузки на callback-кнопке.

    В VK callback-кнопка обязана получить ответ через sendMessageEventAnswer,
    иначе на iOS/Android кнопка может бесконечно крутиться.

    Сначала пробуем самый тихий вариант — без event_data. Если версия vkbottle/API
    не принимает такой вызов, используем проверенный blank-answer event_data="".
    """
    event_id = _event_value(event, "event_id")
    user_id = _event_value(event, "user_id")
    peer_id = _event_value(event, "peer_id")

    if not (event_id and user_id and peer_id):
        print(
            "[CALLBACK ANSWER WARNING] missing ids",
            f"event_id={event_id!r}",
            f"user_id={user_id!r}",
            f"peer_id={peer_id!r}",
        )
        return

    try:
        # Лучший вариант: просто подтвердить событие без действия в клиенте VK.
        await event.ctx_api.messages.send_message_event_answer(
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id,
        )
        return
    except Exception as error:
        print(f"[CALLBACK ANSWER INFO] answer without event_data failed: {error!r}")

    try:
        # Запасной вариант: пустой event_data убирает бесконечный кружок.
        await event.ctx_api.messages.send_message_event_answer(
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data="",
        )
    except Exception as error:
        print(f"[CALLBACK ANSWER ERROR] blank answer failed: {error!r}")


async def route_callback(event: MessageEvent) -> None:
    action = get_callback_action(event)
    ctx = CallbackMessageContext(event)

    print(
        "[CALLBACK]",
        f"action={action!r}",
        f"user_id={ctx.from_id}",
        f"peer_id={ctx.peer_id}",
        f"cmid={ctx.conversation_message_id}",
    )

    if not action:
        await _answer_callback(event)
        return

    # Отвечаем VK сразу, чтобы кнопка не зависала с кружком.
    await _answer_callback(event)

    try:
        if action in START_ACTIONS:
            await courier.start_handler(ctx)
            return

        if action in ROLE_SELECT_ACTIONS:
            await courier.select_role_handler(ctx)
            return

        if action in ADMIN_ACTIONS:
            if not admin.is_admin(ctx.from_id):
                await courier.start_handler(ctx)
                return

            await ADMIN_ACTIONS[action](ctx)
            return

        if action in COURIER_ACTIONS:
            await COURIER_ACTIONS[action](ctx)
            return

        print(f"[CALLBACK WARNING] Unknown action: {action!r}")

    except Exception as error:
        print(f"[CALLBACK HANDLER ERROR] action={action!r}: {error!r}")
        raise


def register_callback_handlers(bot: Bot) -> None:
    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent)
    async def handle_message_event(event: MessageEvent):
        await route_callback(event)
