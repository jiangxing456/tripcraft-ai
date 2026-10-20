from sqlalchemy import Text, DateTime
from datetime import datetime, timezone
from typing import Optional
from cuid2 import Cuid

CUID_GENERATOR: Cuid = Cuid()

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TripPlanStatus(Base):
    """行程生成过程的实时状态（前端轮询这张表来看进度到哪一步了）。"""

    __tablename__ = "trip_plan_status"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: CUID_GENERATOR.generate()
    )
    tripPlanId: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    currentStep: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    startedAt: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    completedAt: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


class TripPlanOutput(Base):
    """行程生成完之后的产物：itinerary（行程正文）+ summary（摘要）。"""

    __tablename__ = "trip_plan_output"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: CUID_GENERATOR.generate()
    )
    tripPlanId: Mapped[str] = mapped_column(Text, index=True)
    itinerary: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
