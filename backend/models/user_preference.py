"""
用户偏好模型 —— 映射 user_preferences 表（长期记忆的存储层）。

用 SQLAlchemy 2.0 声明式 ORM 映射，列名是
snake_case（与 migrations/create_user_preferences_table.sql 一一对齐）。

一张表存一个用户的所有长期偏好，每条一行：
    - category 区分维度（hotel/dining/pace/budget/transport/general）
    - content  是一句话描述，由 LLM 从历史旅行里抽取出来
"""

from datetime import datetime, timezone

from sqlalchemy import Text, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from cuid2 import Cuid

CUID_GENERATOR: Cuid = Cuid()


class Base(DeclarativeBase):
    pass


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category", name="uq_user_preferences_user_category"
        ),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(CUID_GENERATOR.generate())
    )
    user_id: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    source_trip_id: Mapped[str] = mapped_column(Text, default="")
    # 时间列统一 naive UTC（与 trip_db.py 约定一致），写入前 .replace(tzinfo=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
