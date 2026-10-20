"""只测关键约束和真实 LangGraph 的分支/暂停/恢复，不调用付费服务。"""

import asyncio
import json
from decimal import Decimal

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langchain_core.messages import AIMessage, ToolMessage

import services.planner as planner
from models.travel_plan import TravelPlanRequest, TravelDates
from router.planner import normalize
from services.planner import build_graph, sample_draft, validate


def request(budget=3000):
    return TravelPlanRequest(
        starting_location="北京",
        destination="成都",
        duration=3,
        travel_dates=TravelDates(start="2026-10-28", end="2026-10-30"),
        budget=budget,
        budget_currency="CNY",
    )


class TravelTool:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args["kind"])
        prices = {
            "flight": 900,
            "hotel": 550 if args["affordable"] else 1400,
            "dining": 120,
            "destination": 180,
        }
        return {
            "name": "测试样本",
            "unit_price": prices[args["kind"]],
            "currency": "CNY",
            "source": "fixture://" + args["kind"],
        }


class Cache:
    def __init__(self):
        self.items = {}

    async def get(self, key):
        return self.items.get(key)

    async def set(self, key, value, ex):
        assert ex == 300
        self.items[key] = value


def initial(req, approval=True):
    return {
        "request": req.model_dump(),
        "demo": True,
        "approval": approval,
        "research": {},
        "cache_hits": {},
        "attempts": 0,
        "status": "running",
    }


def test_replan_pause_resume_and_cache():
    async def run():
        tool, cache = TravelTool(), Cache()
        graph = build_graph(InMemorySaver(), [tool], cache)
        config = {"configurable": {"thread_id": "test"}}
        state = await graph.ainvoke(initial(request()), config)
        assert state["status"] == "awaiting_approval"
        assert state["total"] == "2540" and state["attempts"] == 1
        assert tool.calls.count("flight") == 1 and tool.calls.count("hotel") == 2
        assert (await graph.aget_state(config)).interrupts
        state = await graph.ainvoke(Command(resume={"action": "approve"}), config)
        assert state["status"] == "completed"
        state = await graph.ainvoke(
            initial(request(), approval=False),
            {"configurable": {"thread_id": "second"}},
        )
        assert state["status"] == "completed"
        assert all(state["cache_hits"].values())
        assert len(tool.calls) == 5  # 第二次全部来自缓存，包括低价酒店。

    asyncio.run(run())


def test_unreachable_budget_stops_and_user_can_revise():
    async def run():
        graph = build_graph(InMemorySaver(), [TravelTool()])
        config = {"configurable": {"thread_id": "tight-budget"}}
        state = await graph.ainvoke(initial(request(1000)), config)
        assert state["status"] == "needs_review" and state["attempts"] == 2
        assert state["issues"] and state["total"] == "2540"
        state = await graph.ainvoke(
            Command(resume={"action": "revise", "budget": 3000}), config
        )
        assert state["status"] == "awaiting_approval" and state["issues"] == []

    asyncio.run(run())


def test_money_dates_currency_and_quantities_are_checked():
    research = {
        k: {
            "name": "样本",
            "unit_price": 10,
            "currency": "CNY",
            "source": "fixture://" + k,
        }
        for k in ["flight", "hotel", "dining", "destination"]
    }
    draft = sample_draft(request(), research)
    draft.expenses[0].unit_price = Decimal("0.10")
    draft.expenses[1].unit_price = Decimal("0.20")
    assert validate(draft, request())[1] == Decimal("40.50")
    draft.expenses[0].currency = "USD"
    draft.expenses[1].quantity = 99
    draft.itinerary.day_by_day_plan[0].date = "2026-10-01"
    issues, _ = validate(draft, request())
    assert any("币种" in x for x in issues)
    assert any("数量" in x for x in issues)
    assert any("日期" in x for x in issues)


@pytest.mark.parametrize(
    "change",
    [
        dict(duration=0),
        dict(budget=-1),
        dict(adults=0),
        dict(user_id="someone-else"),
        dict(
            travel_dates=TravelDates(start="2026-10-28").model_copy(
                update={"start": "next week"}
            )
        ),
    ],
)
def test_api_rejects_invalid_input(change):
    with pytest.raises(HTTPException):
        normalize(request().model_copy(update=change))


def test_non_budget_issue_does_not_trigger_hotel_repair():
    class WrongCurrencyTool(TravelTool):
        async def ainvoke(self, args):
            quote = await super().ainvoke(args)
            if args["kind"] == "hotel":
                quote["currency"] = "USD"
            return quote

    async def run():
        tool = WrongCurrencyTool()
        graph = build_graph(InMemorySaver(), [tool])
        config = {"configurable": {"thread_id": "currency-review"}}
        state = await graph.ainvoke(initial(request(), approval=False), config)
        assert state["status"] == "needs_review"
        assert state["attempts"] == 0
        assert tool.calls.count("hotel") == 1
        assert any("币种" in issue for issue in state["issues"])

    asyncio.run(run())


def test_model_branch_preserves_tool_evidence_and_replanning(monkeypatch):
    tool = TravelTool()
    quotes = {}

    class Agent:
        async def ainvoke(self, payload, config):
            arguments = json.loads(payload["messages"][0][1])
            quote = await tool.ainvoke(arguments)
            quotes[arguments["kind"]] = quote
            return {
                "messages": [
                    ToolMessage(
                        content=[{"type": "text", "text": json.dumps(quote)}],
                        tool_call_id="travel-search",
                    ),
                    AIMessage(content="资料已查询，保留工具来源"),
                ]
            }

    async def convert(prompt, model):
        assert model is planner.Draft
        return sample_draft(request(), quotes).model_dump_json()

    monkeypatch.setattr(planner, "get_model", lambda: object())
    monkeypatch.setattr(planner, "create_agent", lambda *args, **kwargs: Agent())
    monkeypatch.setattr(planner, "convert_to_model", convert)

    async def run():
        graph = build_graph(InMemorySaver(), [tool])
        input_state = initial(request(), approval=False)
        input_state["demo"] = False
        config = {"configurable": {"thread_id": "model-tools"}}
        state = await graph.ainvoke(input_state, config)
        assert state["status"] == "completed"
        assert state["total"] == "2540"
        assert state["attempts"] == 1
        for role, result in state["research"].items():
            assert result["evidence"][0]["source"] == "fixture://" + role

    asyncio.run(run())
