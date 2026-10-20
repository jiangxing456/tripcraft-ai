"""同一事务内保存结果，不先删除旧产物。"""

from datetime import datetime, timezone
from sqlalchemy import select
from models.trip_db import TripPlanStatus, TripPlanOutput
from services.db_service import get_db_session


async def set_status(trip_id: str, status: str, step: str, error: str = ""):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with get_db_session() as session:
        row = await session.scalar(
            select(TripPlanStatus).where(TripPlanStatus.tripPlanId == trip_id)
        )
        if row is None:
            row = TripPlanStatus(tripPlanId=trip_id)
            session.add(row)
        row.status = status
        row.currentStep = step
        row.error = error
        if status == "processing":
            row.startedAt = now
            row.completedAt = None
        elif status in {"completed", "failed"}:
            row.completedAt = now
        row.updatedAt = now
        await session.commit()


async def save_output(trip_id: str, itinerary: str):
    async with get_db_session() as session:
        row = await session.scalar(
            select(TripPlanOutput).where(TripPlanOutput.tripPlanId == trip_id)
        )
        if row is None:
            session.add(
                TripPlanOutput(tripPlanId=trip_id, itinerary=itinerary, summary="")
            )
        else:
            row.itinerary = itinerary
            row.updatedAt = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
