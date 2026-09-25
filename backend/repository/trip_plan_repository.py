"""
行程计划仓储层 —— trip_plan_status / trip_plan_output 两张表的全部读写入口。

分工：本层只管「跟数据库打交道」，不含任何业务判断。什么时候置 processing、
什么时候落 itinerary，都由 services/plan_service.py 编排（该文件按步骤调用这里）。

约定（与 models/trip_db.py 的模型定义配套）：
    1. 时间列是 timestamp without time zone，所有 datetime 写入前都要 .replace(tzinfo=None)
       降成 naive UTC；否则拿库里读回来的 naive 值去算差，Python 会抛 TypeError。
    2. 单行查询统一用 scalar_one_or_none()：查不到返回 None；查出多行会抛
       MultipleResultsFound（engine/result.py:813）——所以依赖 tripPlanId 事实上唯一，
       而 DDL 里的 idx_*_trip_plan_id 只是普通索引，没有唯一约束兜底。
    3. 更新走「查出来 → 改属性 → commit」的 ORM 方式，不做 bulk UPDATE，
       这样模型上的 onupdate 才会生效。

参考出处（对应本机安装的 SQLAlchemy 2.0.41，路径相对 backend/）：
    - select()：sqlalchemy/sql/_selectable_constructors.py:496
    - delete()：sqlalchemy/sql/_dml_constructors.py:111
    - scalar_one_or_none()：sqlalchemy/engine/result.py:1479
    - AsyncSession.commit() / refresh()：sqlalchemy/ext/asyncio/session.py:1006、:311
    - 异步 ORM 文档：https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
"""

from datetime import datetime, timezone
from typing import Optional, List
# 2.0 风格：select()/delete() 是「先构造语句对象、再交给 session 执行」，
# 取代 1.x 的 session.query() 链式写法（_selectable_constructors.py:496、_dml_constructors.py:111）
from sqlalchemy import select, delete

from models.trip_db import TripPlanStatus, TripPlanOutput
from services.db_service import get_db_session


async def create_trip_plan_status(
    trip_plan_id: str, status: str = "pending", current_step: Optional[str] = None
) -> TripPlanStatus:
    """新建一条状态记录（一个 tripPlanId 只建一次）。

    调用方：services/plan_service.py:286 —— 开工前先确认状态行在不在，不在才建。
    """
    async with get_db_session() as session:
        status_entry = TripPlanStatus(
            tripPlanId=trip_plan_id,
            status=status,
            currentStep=current_step,
            # 显式传时间就绕过了模型里的 default=（models/trip_db.py:80-90）。
            # ⚠️ 这两行用的是 datetime.now()，取的是「本机时区的墙上时间」；
            #    而本文件其余地方（update_trip_plan_status / create_trip_plan_output）
            #    用的是 datetime.now(timezone.utc)。两者口径不一致，非 UTC 时区下
            #    同一个业务的 createdAt 与 updatedAt 会差出一个时区偏移量。
            createdAt=datetime.now().replace(tzinfo=None),
            updatedAt=datetime.now().replace(tzinfo=None),
        )
        # add() 是同步方法，不用 await —— 它只是把对象挂到 Session 的待写队列，
        # 真正的 INSERT 发生在 commit() 时
        session.add(status_entry)
        # commit 落库后 refresh：从库里回读真实值（默认值、触发器写入的列）覆盖到对象上，
        # 保证函数返回的实例和库里完全一致
        await session.commit()
        await session.refresh(status_entry)
        return status_entry


async def get_trip_plan_status(trip_plan_id: str) -> Optional[TripPlanStatus]:
    """按 tripPlanId 查状态行；查不到返回 None（不抛异常，调用方直接 if not 判空）。"""
    async with get_db_session() as session:
        result = await session.execute(
            select(TripPlanStatus).where(TripPlanStatus.tripPlanId == trip_plan_id)
        )
        # scalar_one_or_none()：0 行 → None；多于 1 行 → 抛 MultipleResultsFound。
        # 这里能这么写是默认 tripPlanId 唯一，但库里只有普通索引、没有唯一约束兜底，
        # 一旦漏建出重复行，这里会从「返回数据」变成「抛异常」。
        return result.scalar_one_or_none()


async def update_trip_plan_status(
    trip_plan_id: str,
    status: str,
    current_step: Optional[str] = None,
    
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> Optional[TripPlanStatus]:
    """推进状态；记录不存在时返回 None（不抛异常，上层无需 try）。

    这是「部分更新」：只有显式传进来的字段会被覆盖，没传的保持原值 ——
    所以 plan_service 里给 6 个 Agent 推进度时，每次只带 status + current_step 就够。

    副作用：判空用的是 `is not None`，传 None 一律被当作「这一列不动」，
    即 「把 error 清空」是做不到的，只能传空串 ""。

    Args:
        status: 必填，每次调用都会覆盖
        started_at / completed_at: 传进来的是 aware 时间（调用方一律给 datetime.now(timezone.utc)），
            写库前在这里统一去掉 tzinfo，跟 timestamp without time zone 的列类型对齐
    """
    async with get_db_session() as session:
        result = await session.execute(
            select(TripPlanStatus).where(TripPlanStatus.tripPlanId == trip_plan_id)
        )
        status_entry = result.scalar_one_or_none()

        if status_entry:
            status_entry.status = status
            if current_step is not None:
                status_entry.currentStep = current_step
            if error is not None:
                status_entry.error = error
            if started_at is not None:
                status_entry.startedAt = started_at.replace(tzinfo=None)
            if completed_at is not None:
                status_entry.completedAt = completed_at.replace(tzinfo=None)
            # 手动刷 updatedAt（UTC naive），与模型上的 onupdate 双保险。
            # 但注意 DDL 里还有 BEFORE UPDATE 触发器 update_trip_plan_status_updated_at，
            # 它会把这一列改写成 CURRENT_TIMESTAMP —— 所以最终落库的是触发器的值
            # （取决于数据库会话的 TimeZone 设置），这里赋的值只对「不触发触发器」的场景有意义；
            # 后面 refresh() 回读到的也是触发器写的那个值。
            status_entry.updatedAt = datetime.now(timezone.utc).replace(tzinfo=None)

            await session.commit()
            await session.refresh(status_entry)
        return status_entry


async def create_trip_plan_output(
    trip_plan_id: str, itinerary: str, summary: Optional[str] = None
) -> TripPlanOutput:
    """新建一条产物记录。

    itinerary 列（text）里存的不是纯文本行程，而是 plan_service.py:522 拼好的整段 JSON 字符串：
    结构化行程 + 6 个 Agent 的原始 Markdown 回答全在里面 —— 所以这一列会很大，
    查询时别顺手 select 全表。
    """
    async with get_db_session() as session:
        output_entry = TripPlanOutput(
            tripPlanId=trip_plan_id,
            itinerary=itinerary,
            summary=summary,
            createdAt=datetime.now(timezone.utc).replace(tzinfo=None),
            updatedAt=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(output_entry)
        await session.commit()
        await session.refresh(output_entry)
        return output_entry


async def get_trip_plan_output(trip_plan_id: str) -> Optional[TripPlanOutput]:
    """按 tripPlanId 查产物；没有则返回 None。"""
    async with get_db_session() as session:
        result = await session.execute(
            select(TripPlanOutput).where(TripPlanOutput.tripPlanId == trip_plan_id)
        )
        return result.scalar_one_or_none()


async def update_trip_plan_output(
    trip_plan_id: str, itinerary: Optional[str] = None, summary: Optional[str] = None
) -> Optional[TripPlanOutput]:
    """部分更新产物：只覆盖传进来的字段（语义同 update_trip_plan_status）。

    上游目前不用这个函数 —— plan_service 的覆盖式落库是先 delete 再 create
    （plan_service.py:519、:534），留在这里是给「只改摘要」这类场景备用。
    同样因为判空用 `is not None`：summary 一旦写过就清不掉（传 None 表示不改）。
    """
    async with get_db_session() as session:
        result = await session.execute(
            select(TripPlanOutput).where(TripPlanOutput.tripPlanId == trip_plan_id)
        )
        output_entry = result.scalar_one_or_none()

        if output_entry:
            if itinerary is not None:
                output_entry.itinerary = itinerary
            if summary is not None:
                output_entry.summary = summary
            output_entry.updatedAt = datetime.now(timezone.utc).replace(tzinfo=None)

            await session.commit()
            await session.refresh(output_entry)
        return output_entry


# ---------------------------------------------------------------------------
# 下面三个是「按状态捞一批」的查询，前两个只是 get_trip_plans_by_status 的便捷封装
# （给服务重启后巡检未完成任务之类的场景用）。注意两点：
#   1. status 是裸字符串：库里没有 CHECK 约束、Python 侧也没有枚举，
#      合法值全凭约定 —— 必须与 plan_service.py 里写死的
#      "pending" / "processing" / "completed" / "failed" 保持一致，改一边要改两边。
#   2. 没有 ORDER BY、也没有分页，返回顺序由 PostgreSQL 决定；表大了要补齐。
# ---------------------------------------------------------------------------
async def get_all_pending_trip_plans() -> List[TripPlanStatus]:
    """取所有 status='pending' 的行程。"""
    async with get_db_session() as session:
        result = await session.execute(
            select(TripPlanStatus).where(TripPlanStatus.status == "pending")
        )
        return list(result.scalars().all())


async def get_all_processing_trip_plans() -> List[TripPlanStatus]:
    """取所有 status='processing' 的行程（通常是上次进程挂掉时卡住的）。"""
    async with get_db_session() as session:
        result = await session.execute(
            select(TripPlanStatus).where(TripPlanStatus.status == "processing")
        )
        # scalars() 取出「第一列」的标量流（这里就是 ORM 实体），再摊平成 list
        return list(result.scalars().all())


async def get_trip_plans_by_status(status: str) -> List[TripPlanStatus]:
    """取指定状态的全部行程（上面两个函数的通用版）。"""
    async with get_db_session() as session:
        result = await session.execute(
            select(TripPlanStatus).where(TripPlanStatus.status == status)
        )
        return list(result.scalars().all())


async def delete_trip_plan_outputs(trip_plan_id: str) -> None:
    """按 tripPlanId 删掉全部产物行。

    配合 plan_service.py:519 的「先删后建」实现覆盖式落库 —— 重新生成计划时不会堆历史版本，
    因此一个 tripPlanId 正常只会有一行产物（get_trip_plan_output 就是靠这点用 scalar_one_or_none）。
    这里走 SQL 级 DELETE：一条语句直接删，不用把行加载进 Session 再逐行删。
    返回 None —— 不告诉调用方删了几行（想判断「有没有删到」得自己先查）。
    """
    async with get_db_session() as session:
        await session.execute(
            delete(TripPlanOutput).where(TripPlanOutput.tripPlanId == trip_plan_id)
        )
        await session.commit()
