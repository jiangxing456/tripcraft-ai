"""重复提交不能启动第二个任务；模型空结果不能伪装成成功。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from fastapi import HTTPException
import agents.structured_output as structured
import router.plan as route
from models.travel_plan import TravelPlanAgentRequest, TravelPlanRequest, TravelDates


def test_duplicate_submission_and_task_cleanup(monkeypatch):
    async def check():
        gate = asyncio.Event()

        async def generate(*args):
            await gate.wait()

        monkeypatch.setattr(route, "generate_travel_plan", generate)
        planner = SimpleNamespace(tasks={})
        http_request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(planner=planner))
        )
        body = TravelPlanAgentRequest(
            trip_plan_id="test",
            travel_plan=TravelPlanRequest(
                starting_location="北京",
                destination="成都",
                travel_dates=TravelDates(start="2026-10-28"),
            ),
        )
        assert (await route.trigger_trip_craft_agent(body, http_request)).success
        with pytest.raises(HTTPException) as error:
            await route.trigger_trip_craft_agent(body, http_request)
        assert error.value.status_code == 409
        task = planner.tasks["test"]
        gate.set()
        await task
        await asyncio.sleep(0)
        assert not planner.tasks

    asyncio.run(check())


def test_empty_structured_response_is_failure(monkeypatch):
    model = Mock()
    model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=None)
    monkeypatch.setattr(structured, "get_model", lambda: model)
    with pytest.raises(ValueError, match="没有返回"):
        asyncio.run(structured.convert_to_model("test", TravelDates))
