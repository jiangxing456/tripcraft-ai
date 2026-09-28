"""
行程表模型 —— 用 SQLAlchemy 2.0 声明式 ORM 映射 trip_plan_status / trip_plan_output 两张表。
把 PostgreSQL 里的表映射成 Python 类（SQLAlchemy ORM），就是这个文件的主要作用。
字段不是随手定的，而是跟 migrations/create_trip_plan_tables.sql 一比一对齐的
（列名大小写、可空性、默认值都靠那张 DDL 说话）。改表结构时两边必须一起改。

参考出处（对应本机安装的 SQLAlchemy 2.0.41，路径相对 backend/）：
    - 声明式映射总览：https://docs.sqlalchemy.org/en/20/orm/declarative_mapping.html
    - 声明列与类型：  https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html
    - 本机源码：.venv/Lib/site-packages/sqlalchemy/orm/decl_api.py:633（DeclarativeBase）、
                .venv/Lib/site-packages/sqlalchemy/orm/_orm_constructors.py:97（mapped_column）、
                .venv/Lib/site-packages/sqlalchemy/sql/sqltypes.py:735（DateTime）
    - 建表 DDL：migrations/create_trip_plan_tables.sql
"""

from sqlalchemy import Column, String,  Text, DateTime
from datetime import datetime, timezone
from typing import Optional
from cuid2 import Cuid

# CUID2 生成器：默认产出 24 位的 base36 字符串（cuid2/generator.py:20、:24）。
# 注意它是「应用侧默认值」——INSERT 时由 Python 现算一个，不依赖数据库自增，
# 所以下面主键都写 default=... 而不是 server_default=...。
CUID_GENERATOR: Cuid = Cuid()

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """2.0 风格的声明式基类（decl_api.py:633）。本文件的三个模型都挂在它下面。

    （models/plan_task.py 另起了一个自己的 Base，两边的 metadata 互不相干。）
    """
    pass


class TripPlan(Base):
    """占位模型：trip_plan 主表不归这个后端建（表结构在别处维护）。

    这里只是留个「壳」，让关系/外键有个落点，所以没有任何业务字段。
    """

    __tablename__ = (
        "trip_plan"  # Assuming this table exists as per foreign key constraints
    )
    id = Column(
        String, primary_key=True, default=lambda: str(CUID_GENERATOR.generate())
    )
    # Add other fields for TripPlan if needed for standalone model definition
    # For this task, we only need it to satisfy relationship constraints if defined from this end.


class TripPlanStatus(Base):
    """行程生成过程的实时状态（前端轮询这张表来看进度到哪一步了）。"""

    __tablename__ = "trip_plan_status"

    # 属性名用驼峰，是为了跟 DDL 里带双引号的大小写敏感列名逐字对齐：
    # "tripPlanId" 这类名字一旦少了引号就会被 PostgreSQL 折成小写，所以 SQLAlchemy
    # 对含大写字母的标识符会自动加引号（实测生成的是 trip_plan_status."tripPlanId"）。
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: CUID_GENERATOR.generate()
    )
    # index=True 对应 DDL 里的 idx_trip_plan_status_trip_plan_id；
    # 建表本身由 migrations 的 SQL 负责，这里主要是把「该有索引」这件事记在模型上。
    tripPlanId: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    currentStep: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 时间列统一用 DateTime(timezone=False)：timezone 的库默认值就是 False（sqltypes.py:757），
    # 映射到 PostgreSQL 是 timestamp without time zone，跟 DDL 一致。
    # 因此写入前都得 .replace(tzinfo=None) 把「aware」时间降成 naive UTC；
    # 否则拿库里读回来的 naive 值去减 aware 值，Python 会直接抛 TypeError。
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
    # onupdate 是应用层兜底：DDL 里虽然已经有 update_updated_at_column() 触发器
    # 会在 UPDATE 时刷 "updatedAt"，但只走 ORM 的场景下由这里保证同样效果。
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
    # 同样对应 DDL 里的 idx_trip_plan_output_trip_plan_id
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

