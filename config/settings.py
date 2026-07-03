from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Не задана переменная окружения {name}")
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "да"}


VK_TOKEN = _required("VK_TOKEN")

# Callback API / Vercel
VK_CONFIRMATION_CODE = os.getenv("VK_CONFIRMATION_CODE", "").strip()
VK_SECRET_KEY = os.getenv("VK_SECRET_KEY", "").strip()
VK_API_VERSION = os.getenv("VK_API_VERSION", "5.199").strip()

ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in os.getenv("ADMIN_IDS", "").split(",")
    if admin_id.strip()
]

# Можно задать одной строкой, например из Neon/Supabase/Railway:
# DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

DB_HOST = os.getenv("DB_HOST", "localhost").strip()
DB_PORT = os.getenv("DB_PORT", "5432").strip()
DB_NAME = os.getenv("DB_NAME", "sushi_queue").strip()
DB_USER = os.getenv("DB_USER", "postgres").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "").strip()

DB_ECHO = _bool_env("DB_ECHO", False)
DB_USE_NULLPOOL = _bool_env("DB_USE_NULLPOOL", bool(os.getenv("VERCEL")))
VK_VERIFY_SSL = _bool_env("VK_VERIFY_SSL", True)

DEFAULT_LOCATION_NAME = os.getenv("DEFAULT_LOCATION_NAME", "Основная точка").strip()
