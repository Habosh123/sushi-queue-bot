import json


BUTTON_COLORS = {"primary", "secondary", "positive", "negative"}

SUPPORT_ADMIN_ID = 1118718076
SUPPORT_ADMIN_DIALOG_URL = f"https://vk.com/im?sel={SUPPORT_ADMIN_ID}"


def _payload(action: str | None) -> str | None:
    if not action:
        return None

    return json.dumps(
        {"action": action},
        ensure_ascii=False,
    )


def make_callback_button(
    label: str,
    color: str = "secondary",
    action: str | None = None,
) -> dict:
    """
    Callback-кнопка не отправляет текстовое сообщение в чат.
    VK присылает событие message_event, которое обрабатывается в handlers/callbacks.py.
    """
    if color not in BUTTON_COLORS:
        color = "secondary"

    button = {
        "action": {
            "type": "callback",
            "label": label,
        },
        "color": color,
    }

    payload = _payload(action)

    if payload:
        button["action"]["payload"] = payload

    return button


def make_link_button(label: str, link: str) -> dict:
    return {
        "action": {
            "type": "open_link",
            "label": label,
            "link": link,
        }
    }


def admin_contact_button() -> dict:
    return make_link_button(
        "📞 Написать администратору",
        SUPPORT_ADMIN_DIALOG_URL,
    )


def build_keyboard(buttons: list[list[dict]]) -> str:
    return json.dumps(
        {
            "one_time": False,
            "inline": False,
            "buttons": buttons,
        },
        ensure_ascii=False,
    )


def role_select_keyboard() -> str:
    return build_keyboard(
        [
            [make_callback_button("🛡 Админ-панель", "primary", "open_admin")],
            [make_callback_button("🚚 Меню курьера", "positive", "open_courier")],
        ]
    )


def access_denied_keyboard() -> str:
    return build_keyboard(
        [
            [admin_contact_button()],
        ]
    )


def courier_ready_keyboard() -> str:
    return build_keyboard(
        [
            [make_callback_button("🚚 Занять очередь", "positive", "courier_join")],
            [admin_contact_button()],
        ]
    )


def courier_in_queue_keyboard() -> str:
    return build_keyboard(
        [
            [make_callback_button("🔄 Обновить", "primary", "courier_refresh")],
            [make_callback_button("❌ Покинуть очередь", "negative", "courier_leave_start")],
            [admin_contact_button()],
        ]
    )


def leave_queue_confirm_keyboard() -> str:
    return build_keyboard(
        [
            [
                make_callback_button("✅ Да, покинуть", "negative", "courier_leave_confirm"),
                make_callback_button("❌ Нет, остаться", "primary", "courier_leave_cancel"),
            ],
            [admin_contact_button()],
        ]
    )


def admin_main_keyboard() -> str:
    return build_keyboard(
        [
            [make_callback_button("🚀 Вызвать", "positive", "admin_call")],
            [make_callback_button("📋 Очередь", "primary", "admin_queue")],
            [make_callback_button("👥 Управление курьерами", "primary", "admin_couriers")],
            [make_callback_button("🔄 Обновить", "secondary", "admin_refresh")],
            [make_callback_button("🧹 Очистить очередь", "negative", "admin_clear_queue")],
            [make_callback_button("🔀 Выбор режима", "secondary", "select_role")],
        ]
    )


def admin_couriers_keyboard() -> str:
    return build_keyboard(
        [
            [make_callback_button("➕ Добавить курьера", "positive", "admin_add_courier")],
            [make_callback_button("➖ Удалить курьера", "negative", "admin_remove_courier")],
            [make_callback_button("📋 Список всех курьеров", "primary", "admin_couriers_list")],
            [make_callback_button("⬅️ Назад", "secondary", "admin_back")],
        ]
    )


def clear_queue_confirm_keyboard() -> str:
    return build_keyboard(
        [
            [
                make_callback_button("✅ Да, очистить", "negative", "admin_clear_confirm"),
                make_callback_button("❌ Нет, отмена", "primary", "admin_clear_cancel"),
            ]
        ]
    )
