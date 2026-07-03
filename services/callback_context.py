from __future__ import annotations

import json
from typing import Any


class CallbackMessageContext:
    """
    Обёртка над VK message_event.
    Делает callback-событие похожим на обычный Message, чтобы admin.py и courier.py
    использовали ту же бизнес-логику.
    """

    def __init__(self, event: Any):
        self.event = event
        self.ctx_api = getattr(event, "ctx_api", None)
        self.peer_id = _event_value(event, "peer_id")
        self.from_id = _event_value(event, "user_id", "from_id")
        self.text = ""
        self.payload = _event_payload(event)
        self.is_callback_context = True

        self.conversation_message_id = _event_value(
            event,
            "conversation_message_id",
            "cmid",
        )
        self.message_id = _event_value(event, "message_id", "id")

    async def answer(self, text: str, keyboard: str | None = None):
        """
        Для callback-кнопок сначала пробуем редактировать то сообщение бота,
        под которым была нажата кнопка. Так чат не засоряется новыми сообщениями.
        Если VK не даст отредактировать сообщение — отправляем новое.
        """
        if self.conversation_message_id:
            try:
                return await self.ctx_api.messages.edit(
                    peer_id=self.peer_id,
                    conversation_message_id=self.conversation_message_id,
                    message=text,
                    keyboard=keyboard,
                )
            except Exception as error:
                print(f"[CALLBACK EDIT ERROR] edit by cmid failed: {error!r}")

        if self.message_id:
            try:
                return await self.ctx_api.messages.edit(
                    peer_id=self.peer_id,
                    message_id=self.message_id,
                    message=text,
                    keyboard=keyboard,
                )
            except Exception as error:
                print(f"[CALLBACK EDIT ERROR] edit by message_id failed: {error!r}")

        return await self.ctx_api.messages.send(
            peer_id=self.peer_id,
            random_id=0,
            message=text,
            keyboard=keyboard,
        )


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


def _event_payload(event: Any) -> dict:
    payload = getattr(event, "payload", None)

    if payload is None:
        obj = getattr(event, "object", None)
        if obj is not None:
            payload = getattr(obj, "payload", None)
            if payload is None and isinstance(obj, dict):
                payload = obj.get("payload")

    if isinstance(payload, dict):
        return payload

    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}

        return parsed if isinstance(parsed, dict) else {}

    return {}


def get_callback_action(event: Any) -> str | None:
    action = _event_payload(event).get("action")
    return action if isinstance(action, str) else None
