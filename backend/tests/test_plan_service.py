"""验证生成失败不覆盖旧结果，偏好失败不推翻已完成的方案。"""

import asyncio
from unittest.mock import AsyncMock
import pytest
import services.plan_service as service
from models.travel_plan import TravelPlanAgentRequest, TravelPlanRequest, TravelDates


class Planner:
    def __init__(self, issues=()):
        self.tasks = {}
        self.issues = list(issues)

    async def run(self, run_id, **kwargs):
        return {
            "issues": self.issues,
            "draft": {"itinerary": {}},
            "total": "2540",
            "research": {"dining": {"content": "餐饮资料"}},
        }


def payload():
    return TravelPlanAgentRequest(
        trip_plan_id="trip-1",
        travel_plan=TravelPlanRequest(
            starting_location="北京",
            destination="成都",
            duration=3,
            travel_dates=TravelDates(start="2026-10-28"),
        ),
    )


def test_failure_does_not_replace_output(monkeypatch):
    status, save = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service, "set_status", status)
    monkeypatch.setattr(service, "save_output", save)
    with pytest.raises(ValueError, match="超预算"):
        asyncio.run(service.generate_travel_plan(payload(), Planner(["超预算"])))
    save.assert_not_called()
    assert status.call_args.args[1] == "failed"


def test_memory_failure_keeps_completed_result(monkeypatch):
    status, save = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service, "set_status", status)
    monkeypatch.setattr(service, "save_output", save)
    monkeypatch.setattr(
        service,
        "extract_and_store",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    output = asyncio.run(service.generate_travel_plan(payload(), Planner()))
    assert "restaurant_agent_response" in output
    save.assert_awaited_once()
    assert status.call_args.args[1] == "completed"
