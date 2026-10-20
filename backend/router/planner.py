"""演示和业务共用同一个图；每次运行使用随机令牌隔离状态。"""

import asyncio
import json
import secrets
from pathlib import Path
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from models.travel_plan import TravelPlanRequest

router = APIRouter()


class Resume(BaseModel):
    action: Literal["approve", "revise"]
    budget: int | None = Field(default=None, gt=0, le=10_000_000)


def normalize(request: TravelPlanRequest):
    if request.user_id:
        raise HTTPException(400, "演示接口不接受用户标识；账户偏好请走已认证的业务接口")
    try:
        return TravelPlanRequest.model_validate(request.model_dump())
    except ValidationError:
        raise HTTPException(400, "日期、天数、人数或预算不合法")


async def authorize(request, run_id, token):
    planner = request.app.state.planner
    state = await planner.state(run_id)
    expected = state.get("token") or planner.tokens.get(run_id)
    if not expected or not token or not secrets.compare_digest(expected, token):
        raise HTTPException(404, "任务不存在或令牌无效")
    return planner, state


@router.get("/demo", include_in_schema=False)
async def demo_page():
    return FileResponse(Path(__file__).resolve().parents[1] / "static" / "planner.html")


@router.get("/api/planner/info")
async def info(request: Request):
    return {
        "demo": request.app.state.planner.demo,
        "checkpoint": request.app.state.checkpoint_backend,
        "redis": request.app.state.redis_available,
    }


@router.post("/api/planner/runs", status_code=202)
async def create_run(body: TravelPlanRequest, request: Request):
    body = normalize(body)
    planner = request.app.state.planner
    run_id = str(uuid4())
    token = secrets.token_urlsafe(24)
    planner.tokens[run_id] = token
    planner.start(run_id, request=body, token=token)
    return {"run_id": run_id, "token": token, "demo": planner.demo}


@router.get("/api/planner/runs/{run_id}")
async def state(run_id: str, request: Request, x_run_token: str = Header(default="")):
    planner, result = await authorize(request, run_id, x_run_token)
    event_log = planner.events.get(run_id, [])
    if event_log:
        last_event = event_log[-1]
        if last_event["node"] == "error":
            result["status"] = "failed"
            result["error"] = last_event["data"]["message"]

    result.pop("token", None)
    result["running"] = run_id in planner.tasks
    return result


@router.post("/api/planner/runs/{run_id}/resume", status_code=202)
async def resume(
    run_id: str, body: Resume, request: Request, x_run_token: str = Header(default="")
):
    planner, state = await authorize(request, run_id, x_run_token)
    is_running = run_id in planner.tasks
    is_paused = state.get("status") in {"awaiting_approval", "needs_review"}
    if is_running or not is_paused:
        raise HTTPException(409, "任务尚未暂停，或已经结束")
    if body.action == "approve" and state.get("issues"):
        raise HTTPException(409, "仍有未满足的约束，请先调整预算或人工处理")
    if body.action == "revise" and body.budget is None:
        raise HTTPException(400, "调整方案需要提供新的预算")
    planner.start(run_id, resume=body.model_dump())
    return {"accepted": True}


@router.get("/api/planner/runs/{run_id}/history")
async def history(run_id: str, request: Request, x_run_token: str = Header(default="")):
    planner, _ = await authorize(request, run_id, x_run_token)
    versions = []
    async for item in planner.checkpointer.alist(planner.config(run_id), limit=30):
        state = item.checkpoint["channel_values"]
        if state.get("draft"):
            versions.append(
                {
                    "checkpoint_id": item.checkpoint["id"],
                    "status": state.get("status"),
                    "total": state.get("total"),
                    "budget": state["request"]["budget"],
                    "attempts": state.get("attempts", 0),
                }
            )
    return {"versions": versions}


@router.get("/api/planner/runs/{run_id}/events")
async def events(
    run_id: str, request: Request, after: int = 0, x_run_token: str = Header(default="")
):
    planner, _ = await authorize(request, run_id, x_run_token)

    async def stream():
        cursor = max(after, 0)
        while not await request.is_disconnected():
            for event in planner.events.get(run_id, [])[cursor:]:
                cursor = event["id"]
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"id: {cursor}\ndata: {data}\n\n"
            if run_id not in planner.tasks:
                yield "event: end\ndata: {}\n\n"
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.3)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
