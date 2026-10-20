"""原 Next.js 入口的落库适配；核心规划只在 planner.py 实现。"""

import json
from loguru import logger
from models.travel_plan import TravelPlanAgentRequest
from repository.trip_plan_repository import set_status, save_output
from services.memory_service import extract_and_store


async def generate_travel_plan(request: TravelPlanAgentRequest, planner) -> str:
    trip_id = request.trip_plan_id
    await set_status(trip_id, "processing", "LangGraph planning")
    try:
        state = await planner.run(trip_id, request=request.travel_plan, approval=False)
        if state["issues"]:
            raise ValueError("；".join(state["issues"]))
        roles = {
            "destination": "destination",
            "flight": "flight",
            "hotel": "hotel",
            "dining": "restaurant",
        }
        output = {
            "itinerary": json.dumps(state["draft"]["itinerary"], ensure_ascii=False),
        }
        for role, value in state["research"].items():
            field = f"{roles[role]}_agent_response"
            output[field] = json.dumps(value, ensure_ascii=False)
        output["budget_agent_response"] = f"核算总价：{state['total']}"
        result = json.dumps(output, ensure_ascii=False)
        await save_output(trip_id, result)
        await set_status(trip_id, "completed", "Plan validated and saved")
    except Exception as exc:
        await set_status(trip_id, "failed", "Planning failed", error=str(exc))
        raise
    try:
        await extract_and_store(
            request.travel_plan.user_id, request.travel_plan.model_dump_json(), trip_id
        )
    except Exception:
        logger.warning("偏好存储失败，保留已经完成的旅行方案")
    return result
