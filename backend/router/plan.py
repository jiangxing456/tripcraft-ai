"""Next.js 业务入口；复用规划图与行程状态，不再维护第二套任务表。"""

import asyncio
from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from models.travel_plan import TravelPlanAgentRequest, TravelPlanResponse
from services.plan_service import generate_travel_plan

router = APIRouter(prefix="/api/plan", tags=["Travel Plan"])


@router.post("/trigger", response_model=TravelPlanResponse)
async def trigger_trip_craft_agent(
    request: TravelPlanAgentRequest, http_request: Request
):
    planner = http_request.app.state.planner
    trip_id = request.trip_plan_id
    if trip_id in planner.tasks:
        raise HTTPException(409, "行程正在生成，请勿重复提交")

    def finished(task):
        if planner.tasks.get(trip_id) is task:
            planner.tasks.pop(trip_id)
        if not task.cancelled() and task.exception():
            logger.error("行程生成失败 {}: {}", trip_id, task.exception())

    task = asyncio.create_task(generate_travel_plan(request, planner))
    planner.tasks[trip_id] = task
    task.add_done_callback(finished)
    return TravelPlanResponse(
        success=True,
        message="Travel plan agent triggered successfully",
        trip_plan_id=trip_id,
    )
