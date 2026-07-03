import json
from typing import Any

from vkbottle.bot import Message


def get_payload(message: Message) -> dict[str, Any]:
    raw_payload = getattr(message, "payload", None)

    if isinstance(raw_payload, dict):
        return raw_payload

    if isinstance(raw_payload, str) and raw_payload.strip():
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return {}

        if isinstance(payload, dict):
            return payload

    return {}


def get_action(message: Message) -> str | None:
    action = get_payload(message).get("action")
    return action if isinstance(action, str) else None


def action_is(expected_action: str):
    def _filter(message: Message) -> bool:
        return get_action(message) == expected_action

    return _filter
