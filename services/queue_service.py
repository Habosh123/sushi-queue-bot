from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config.settings import DEFAULT_LOCATION_NAME
from database.models import DeliveryCall, Location, QueueEntry, User


@dataclass
class QueuePosition:
    position: int
    total: int


@dataclass
class CalledCourier:
    courier_vk_id: int
    courier_name: str
    next_vk_id: int | None
    next_name: str | None


class QueueService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(
        self,
        vk_id: int,
        name: str,
        role: str = "courier",
    ) -> User:
        result = await self.session.execute(
            select(User).where(User.vk_id == vk_id)
        )
        user = result.scalar_one_or_none()

        if user:
            if name:
                user.name = name

            if role == "courier":
                user.role = "courier"

            return user

        user = User(
            vk_id=vk_id,
            name=name or f"Пользователь {vk_id}",
            role=role,
            is_blocked=False,
        )

        self.session.add(user)
        await self.session.flush()

        return user

    async def get_or_create_default_location(self) -> Location:
        result = await self.session.execute(
            select(Location).where(Location.name == DEFAULT_LOCATION_NAME)
        )
        location = result.scalar_one_or_none()

        if location:
            return location

        location = Location(name=DEFAULT_LOCATION_NAME)
        self.session.add(location)
        await self.session.flush()

        return location

    async def is_allowed_courier(self, vk_id: int) -> bool:
        result = await self.session.execute(
            select(User).where(User.vk_id == vk_id)
        )
        user = result.scalar_one_or_none()

        return bool(
            user
            and user.role == "courier"
            and not user.is_blocked
        )

    async def add_courier_by_vk_id(self, vk_id: int) -> User:
        result = await self.session.execute(
            select(User).where(User.vk_id == vk_id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.role = "courier"
            user.is_blocked = False

            if not user.name:
                user.name = f"Курьер {vk_id}"

            await self.session.flush()
            return user

        user = User(
            vk_id=vk_id,
            name=f"Курьер {vk_id}",
            role="courier",
            is_blocked=False,
        )

        self.session.add(user)
        await self.session.flush()

        return user

    async def remove_courier_by_vk_id(self, vk_id: int) -> bool:
        result = await self.session.execute(
            select(User).where(User.vk_id == vk_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        user.is_blocked = True

        active_entries = await self.session.execute(
            select(QueueEntry).where(
                QueueEntry.user_id == user.id,
                QueueEntry.is_active.is_(True),
            )
        )

        for entry in active_entries.scalars().all():
            entry.is_active = False
            entry.left_at = datetime.utcnow()

        await self.session.flush()

        return True

    async def get_couriers_text(self) -> str:
        result = await self.session.execute(
            select(User)
            .where(
                User.role == "courier",
                User.is_blocked.is_(False),
            )
            .order_by(User.name.asc())
        )
        users = result.scalars().all()

        if not users:
            return "📋 Список курьеров пуст."

        lines = ["📋 Список курьеров"]

        for index, user in enumerate(users, start=1):
            lines.append(
                f"{index}. {user.name}\n"
                f"ID: {user.vk_id}"
            )

        return "\n\n".join(lines)

    async def clear_queue(self) -> int:
        location = await self.get_or_create_default_location()

        result = await self.session.execute(
            select(QueueEntry).where(
                QueueEntry.location_id == location.id,
                QueueEntry.is_active.is_(True),
            )
        )
        entries = result.scalars().all()

        for entry in entries:
            entry.is_active = False
            entry.left_at = datetime.utcnow()

        await self.session.flush()

        return len(entries)

    async def join_queue(self, vk_id: int, name: str) -> QueuePosition:
        user = await self.get_or_create_user(vk_id, name, role="courier")
        location = await self.get_or_create_default_location()

        if user.is_blocked:
            raise PermissionError("Пользователь заблокирован")

        result = await self.session.execute(
            select(QueueEntry).where(
                QueueEntry.user_id == user.id,
                QueueEntry.location_id == location.id,
                QueueEntry.is_active.is_(True),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            position = await self.get_position(vk_id)
            if position:
                return position

        entry = QueueEntry(
            user_id=user.id,
            location_id=location.id,
            is_active=True,
            next_notified=False,
        )

        self.session.add(entry)
        await self.session.flush()

        position = await self.get_position(vk_id)

        if not position:
            raise RuntimeError("Не удалось определить позицию в очереди")

        return position

    async def leave_queue(self, vk_id: int) -> bool:
        user_result = await self.session.execute(
            select(User).where(User.vk_id == vk_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return False

        location = await self.get_or_create_default_location()

        result = await self.session.execute(
            select(QueueEntry).where(
                QueueEntry.user_id == user.id,
                QueueEntry.location_id == location.id,
                QueueEntry.is_active.is_(True),
            )
        )
        entry = result.scalar_one_or_none()

        if not entry:
            return False

        entry.is_active = False
        entry.left_at = datetime.utcnow()

        await self.session.flush()

        return True

    async def get_position(self, vk_id: int) -> QueuePosition | None:
        user_result = await self.session.execute(
            select(User).where(User.vk_id == vk_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return None

        location = await self.get_or_create_default_location()

        result = await self.session.execute(
            select(QueueEntry)
            .where(
                QueueEntry.location_id == location.id,
                QueueEntry.is_active.is_(True),
            )
            .order_by(QueueEntry.joined_at.asc(), QueueEntry.id.asc())
        )
        entries = result.scalars().all()

        for index, entry in enumerate(entries, start=1):
            if entry.user_id == user.id:
                return QueuePosition(
                    position=index,
                    total=len(entries),
                )

        return None

    async def get_queue_text(self) -> str:
        location = await self.get_or_create_default_location()

        result = await self.session.execute(
            select(QueueEntry)
            .options(selectinload(QueueEntry.user))
            .where(
                QueueEntry.location_id == location.id,
                QueueEntry.is_active.is_(True),
            )
            .order_by(QueueEntry.joined_at.asc(), QueueEntry.id.asc())
        )
        entries = result.scalars().all()

        if not entries:
            return "📋 Очередь пустая."

        lines = ["📋 Текущая очередь:"]

        for index, entry in enumerate(entries, start=1):
            lines.append(f"{index}. {entry.user.name}")

        return "\n".join(lines)

    async def call_next_courier(
        self,
        admin_vk_id: int,
        admin_name: str,
    ) -> CalledCourier | None:
        admin = await self.get_or_create_user(
            vk_id=admin_vk_id,
            name=admin_name,
            role="admin",
        )

        location = await self.get_or_create_default_location()

        first_result = await self.session.execute(
            select(QueueEntry)
            .options(selectinload(QueueEntry.user))
            .where(
                QueueEntry.location_id == location.id,
                QueueEntry.is_active.is_(True),
            )
            .order_by(QueueEntry.joined_at.asc(), QueueEntry.id.asc())
            .limit(1)
            .with_for_update()
        )
        first_entry = first_result.scalar_one_or_none()

        if not first_entry:
            return None

        first_entry.is_active = False
        first_entry.left_at = datetime.utcnow()

        self.session.add(
            DeliveryCall(
                courier_id=first_entry.user_id,
                admin_id=admin.id,
                location_id=location.id,
            )
        )

        next_result = await self.session.execute(
            select(QueueEntry)
            .options(selectinload(QueueEntry.user))
            .where(
                QueueEntry.location_id == location.id,
                QueueEntry.is_active.is_(True),
            )
            .order_by(QueueEntry.joined_at.asc(), QueueEntry.id.asc())
            .limit(1)
        )
        next_entry = next_result.scalar_one_or_none()

        next_vk_id = None
        next_name = None

        if next_entry and not next_entry.next_notified:
            next_entry.next_notified = True
            next_vk_id = next_entry.user.vk_id
            next_name = next_entry.user.name

        await self.session.flush()

        return CalledCourier(
            courier_vk_id=first_entry.user.vk_id,
            courier_name=first_entry.user.name,
            next_vk_id=next_vk_id,
            next_name=next_name,
        )
