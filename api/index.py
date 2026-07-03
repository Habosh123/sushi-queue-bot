from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any

from sqlalchemy import select
from vkbottle import API

from config.settings import VK_CONFIRMATION_CODE, VK_SECRET_KEY, VK_TOKEN
from database.db import SessionLocal, engine
from database.models import AdminState, Base
from handlers import admin, callbacks, courier

api = API(token=VK_TOKEN)
_tables_ready = False


async def ensure_tables() -> None:
    global _tables_ready

    if _tables_ready:
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _tables_ready = True


async def load_admin_state(vk_id: int) -> None:
    if not admin.is_admin(vk_id):
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(AdminState).where(AdminState.vk_id == vk_id)
        )
        state_row = result.scalar_one_or_none()

    if state_row:
        admin.admin_states[vk_id] = state_row.state
    else:
        admin.admin_states.pop(vk_id, None)


async def persist_admin_state(vk_id: int) -> None:
    if not admin.is_admin(vk_id):
        return

    state = admin.admin_states.get(vk_id)

    async with SessionLocal() as session:
        result = await session.execute(
            select(AdminState).where(AdminState.vk_id == vk_id)
        )
        state_row = result.scalar_one_or_none()

        if state:
            if state_row:
                state_row.state = state
            else:
                session.add(AdminState(vk_id=vk_id, state=state))
        elif state_row:
            await session.delete(state_row)

        await session.commit()


@dataclass
class IncomingMessageContext:
    raw_message: dict[str, Any]

    ctx_api: API = api
    is_callback_context: bool = False

    def __post_init__(self) -> None:
        self.from_id = int(self.raw_message.get("from_id") or 0)
        self.peer_id = int(self.raw_message.get("peer_id") or self.from_id)
        self.text = str(self.raw_message.get("text") or "")
        self.payload = self.raw_message.get("payload") or {}
        self.conversation_message_id = self.raw_message.get("conversation_message_id")
        self.message_id = self.raw_message.get("id")

    async def answer(self, text: str, keyboard: str | None = None):
        return await self.ctx_api.messages.send(
            peer_id=self.peer_id,
            random_id=0,
            message=text,
            keyboard=keyboard,
        )


class CallbackEvent:
    def __init__(self, raw_object: dict[str, Any]):
        self.ctx_api = api
        self.object = raw_object
        self.event_id = raw_object.get("event_id")
        self.user_id = raw_object.get("user_id")
        self.from_id = raw_object.get("user_id")
        self.peer_id = raw_object.get("peer_id")
        self.payload = raw_object.get("payload") or {}
        self.conversation_message_id = raw_object.get("conversation_message_id")
        self.message_id = raw_object.get("message_id") or raw_object.get("id")


ADMIN_TEXT_ROUTES = [
    (admin.admin_action("open_admin", "🛡 Админ-панель", "Админ", "админ"), admin.admin_start_handler),
    (admin.admin_action("admin_call", "🚀 Вызвать"), admin.call_next_handler),
    (admin.admin_action("admin_queue", "📋 Очередь"), admin.admin_queue_handler),
    (admin.admin_action("admin_couriers", "👥 Управление курьерами"), admin.couriers_manage_handler),
    (admin.admin_action("admin_add_courier", "➕ Добавить курьера"), admin.add_courier_start_handler),
    (admin.admin_action("admin_remove_courier", "➖ Удалить курьера"), admin.remove_courier_start_handler),
    (admin.admin_action("admin_couriers_list", "📋 Список всех курьеров"), admin.couriers_list_handler),
    (admin.admin_action("admin_back", "⬅️ Назад"), admin.back_to_admin_main_handler),
    (admin.admin_action("admin_refresh", "🔄 Обновить"), admin.admin_refresh_handler),
    (admin.admin_action("admin_clear_queue", "🧹 Очистить очередь"), admin.clear_queue_start_handler),
    (admin.admin_action("admin_clear_cancel", "❌ Нет, отмена"), admin.clear_queue_cancel_handler),
    (admin.admin_action("admin_clear_confirm", "✅ Да, очистить"), admin.clear_queue_confirm_handler),
]

COURIER_TEXT_ROUTES = [
    (courier.courier_action("open_courier", "🚚 Меню курьера"), courier.open_courier_handler),
    (courier.courier_action("courier_join", "🚚 Занять очередь"), courier.join_queue_handler),
    (courier.courier_action("courier_refresh", "🔄 Обновить", "📋 Очередь"), courier.queue_refresh_handler),
    (courier.courier_action("courier_leave_start", "❌ Покинуть очередь", "❌ Выйти из очереди"), courier.leave_queue_start_handler),
    (courier.courier_action("courier_leave_cancel", "❌ Нет, остаться"), courier.leave_queue_cancel_handler),
    (courier.courier_action("courier_leave_confirm", "✅ Да, покинуть"), courier.leave_queue_confirm_handler),
]


async def handle_message_new(raw_object: dict[str, Any]) -> None:
    message_data = raw_object.get("message") if "message" in raw_object else raw_object

    if not isinstance(message_data, dict):
        return

    ctx = IncomingMessageContext(message_data)

    if not ctx.from_id:
        return

    await load_admin_state(ctx.from_id)

    try:
        if admin.is_admin_waiting_id(ctx):
            if re.fullmatch(admin.ID_REGEXP, ctx.text.strip()):
                await admin.admin_add_or_remove_courier_handler(ctx)
            else:
                await admin.admin_invalid_id_handler(ctx)
            return

        if courier.is_role_select_message(ctx):
            await courier.select_role_handler(ctx)
            return

        for predicate, route_handler in ADMIN_TEXT_ROUTES:
            if predicate(ctx):
                await route_handler(ctx)
                return

        if courier.is_start_message(ctx):
            await courier.start_handler(ctx)
            return

        for predicate, route_handler in COURIER_TEXT_ROUTES:
            if predicate(ctx):
                await route_handler(ctx)
                return

        await courier.start_handler(ctx)

    finally:
        await persist_admin_state(ctx.from_id)


async def handle_message_event(raw_object: dict[str, Any]) -> None:
    if not isinstance(raw_object, dict):
        return

    event = CallbackEvent(raw_object)
    user_id = int(event.user_id or 0)

    if user_id:
        await load_admin_state(user_id)

    try:
        await callbacks.route_callback(event)
    finally:
        if user_id:
            await persist_admin_state(user_id)


async def process_callback(data: dict[str, Any]) -> str:
    await ensure_tables()

    event_type = data.get("type")

    if event_type == "message_new":
        await handle_message_new(data.get("object") or {})
    elif event_type == "message_event":
        await handle_message_event(data.get("object") or {})
    else:
        print(f"[VK CALLBACK] ignored event type={event_type!r}")

    return "ok"


class handler(BaseHTTPRequestHandler):
    def _send_text(self, text: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send_json({"status": "ok", "service": "sushi-queue-bot"})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
            data = json.loads(raw_body or "{}")
        except Exception:
            self._send_text("bad request", status=400)
            return

        if VK_SECRET_KEY:
            secret = str(data.get("secret") or "")
            if secret != VK_SECRET_KEY:
                self._send_text("forbidden", status=403)
                return

        if data.get("type") == "confirmation":
            self._send_text(VK_CONFIRMATION_CODE)
            return

        try:
            result = asyncio.run(process_callback(data))
        except Exception as error:
            print(f"[VK CALLBACK ERROR] {error!r}")
            result = "ok"

        self._send_text(result)
