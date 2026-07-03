# Курьеры Набережная — Vercel Callback API

Версия под Vercel. Long Poll больше не нужен для хостинга: VK будет отправлять события на HTTP endpoint.

## Что важно

- Vercel не хранит локальную базу PostgreSQL, нужна внешняя БД: Neon, Supabase, Railway и т.п.
- Для VK Callback API нужно указать адрес сервера и строку подтверждения.
- Состояние админа при добавлении/удалении курьера хранится в таблице `admin_states`, поэтому ввод VK ID не сломается после cold start.

## Переменные окружения Vercel

Скопируй значения из `.env.example` и задай их в Vercel → Project → Settings → Environment Variables.

```env
VK_TOKEN=токен_сообщества
ADMIN_IDS=511970327,ещё_id_если_нужно

VK_CONFIRMATION_CODE=строка_которую_показывает_VK_для_подтверждения
VK_SECRET_KEY=секретный_ключ_из_Callback_API
VK_API_VERSION=5.199

DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
DB_USE_NULLPOOL=true

DEFAULT_LOCATION_NAME=Основная точка
```

## Endpoint для VK

После деплоя укажи в VK:

```text
https://твой-проект.vercel.app/api/vk
```

В Callback API включи типы событий:

- Входящее сообщение
- Исходящее сообщение
- Действие с сообщением

## Локальный Long Poll

Файл `app.py` оставлен для локального запуска через Long Poll:

```powershell
python app.py
```

На Vercel используется `api/index.py`.
