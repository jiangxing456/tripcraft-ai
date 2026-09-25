"""旅行计划（Travel Plan）相关接口的路由模块。

本模块只暴露一个 HTTP 接口：接收前端提交的行程需求后立即返回，
真正的行程生成放到后台异步任务中执行，并通过任务表持续更新执行状态。
"""

import asyncio
from fastapi import APIRouter, HTTPException, status
from loguru import logger
from models.travel_plan import TravelPlanAgentRequest, TravelPlanResponse
from models.plan_task import TaskStatus
from services.plan_service import generate_travel_plan
from repository.plan_task_repository import create_plan_task, update_task_status

# 路由前缀为 /api/plan，Swagger 文档中归类到 "Travel Plan" 分组
router = APIRouter(prefix="/api/plan", tags=["Travel Plan"])

#前端把表单（已经格式化JSON了）提交到url，然后post到这里plan.py。然后建立任务，返回任务id
@router.post(
    "/trigger",
    response_model=TravelPlanResponse,
    summary="Trigger Trip Craft Agent",
    description="Triggers the travel plan agent with the provided travel details",
)
async def trigger_trip_craft_agent(#async是标记这个函数是异步的，await 才等待
    request: TravelPlanAgentRequest,
) -> TravelPlanResponse:
    """
    触发行程规划 Agent，异步生成个性化的旅行计划。

    该接口不会等待计划生成完成，而是创建后台任务后立即返回，
    调用方需通过 trip_plan_id 自行查询任务状态与结果。

    Args:
        request: 旅行计划请求，包含行程详情（travel_plan）与计划 ID（trip_plan_id）

    Returns:
        TravelPlanResponse: 触发是否成功以及对应的行程计划 ID
    """
    try:
        logger.info(f"Triggering travel plan agent for trip ID: {request.trip_plan_id}")
        logger.info(f"Travel plan details: {request.travel_plan}")

        # 创建初始任务记录，状态为待执行；输入数据即本次行程需求
        task = await create_plan_task(
            trip_plan_id=request.trip_plan_id,
            task_type="travel_plan_generation",
            input_data=request.travel_plan.model_dump(),
        )

        logger.info(f"Task created: {task.id}")

        # 定义后台协程：负责真正生成行程，并同步更新任务状态
        async def generate_plan_with_tracking():
            try:
                # 服务开始执行时，先把任务状态置为「进行中」
                await update_task_status(task.id, TaskStatus.in_progress)
                logger.info(f"Task updated to in progress: {task.id}")

                result = await generate_travel_plan(request)

                # 生成成功：写入输出结果并置为「成功」
                await update_task_status(
                    task.id, TaskStatus.success, output_data={"travel_plan": result}
                )
                logger.info(f"Task updated to success: {task.id}")
            except Exception as e:
                logger.error(f"Error generating travel plan: {str(e)}")
                # 生成失败：记录错误信息并置为「失败」
                await update_task_status(
                    task.id, TaskStatus.error, error_message=str(e)
                )
                logger.info(f"Task updated to error: {task.id}")
                raise#把堆栈打出来。​ 不写的话，你只看到数据库里一条 error 状态，日志里查不到任何线索

        # 丢到后台事件循环中异步执行，不阻塞当前请求的返回
        asyncio.create_task(generate_plan_with_tracking())#create_task 返回的不是结果，是一张票据（Task 对象）​

        logger.info(
            f"Travel plan agent triggered successfully for trip ID: {request.trip_plan_id}"
        )

        # 立即返回触发结果，后续进度由前端轮询任务状态获取
        return TravelPlanResponse(
            success=True,
            message="Travel plan agent triggered successfully",
            trip_plan_id=request.trip_plan_id,
        )

    except Exception as e:
        # 任务创建或调度阶段出错，直接返回 500
        logger.error(f"Error triggering travel plan agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger travel plan agent: {str(e)}",
        )
