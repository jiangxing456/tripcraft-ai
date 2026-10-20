"""按用户和类别原子更新偏好，避免并发规划插入重复记录。"""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from models.user_preference import UserPreference
from services.db_service import get_db_session


async def list_by_user(user_id: str) -> list[UserPreference]:
    async with get_db_session() as session:
        result = await session.scalars(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        return list(result)


async def upsert(
    user_id: str, category: str, content: str, source_trip_id: str
) -> None:
    values = dict(
        user_id=user_id,
        category=category,
        content=content,
        source_trip_id=source_trip_id,
    )
    statement = (
        insert(UserPreference)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["user_id", "category"],
            set_={
                "content": content,
                "source_trip_id": source_trip_id,
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )
    )
    async with get_db_session() as session:
        await session.execute(statement)
        await session.commit()
