"""长期记忆服务（memory_service）的测试。

策略：全程 mock，不连数据库、不调 AI —— 和 test_plan_service.py 一个思路。
测的是 memory_service 自己的编排逻辑：
    - build_context：有/没有偏好、空 user_id 三种情况的返回
    - extract_and_store：正常抽取、转换失败、空 user_id 三种情况

跑法（在 backend 目录下）：
    ./.venv/Scripts/python.exe -m pytest tests/test_memory_service.py -v
"""

import asyncio

import services.memory_service as mem
from models.user_preference import UserPreference


# =====================================================================
# build_context —— 读取路径：把用户偏好拼成注入 prompt 的 markdown
# =====================================================================


def test_build_context_empty_user_id():
    """空 user_id：不查库，直接返回空串（记忆功能自动跳过）。"""
    assert asyncio.run(mem.build_context("")) == ""


def test_build_context_no_preferences(monkeypatch):
    """有 user_id 但没有历史偏好：返回空串。"""

    async def fake_list(user_id):
        return []

    monkeypatch.setattr(mem, "list_by_user", fake_list)
    assert asyncio.run(mem.build_context("user_1")) == ""


def test_build_context_with_preferences(monkeypatch):
    """有偏好：拼出带分类中文标签的 markdown 片段。"""

    async def fake_list(user_id):
        return [
            UserPreference(
                user_id="user_1", category="hotel", content="偏好安静、靠近地铁的酒店"
            ),
            UserPreference(
                user_id="user_1", category="dining", content="爱吃辣，川菜为主"
            ),
        ]

    monkeypatch.setattr(mem, "list_by_user", fake_list)
    result = asyncio.run(mem.build_context("user_1"))

    assert "酒店" in result
    assert "偏好安静、靠近地铁的酒店" in result
    assert "美食" in result
    assert "爱吃辣，川菜为主" in result


# =====================================================================
# extract_and_store —— 写入路径：抽取偏好并入库
# =====================================================================


def test_extract_and_store_empty_user_id():
    """空 user_id：不调 AI、不写库，直接返回 0。"""
    assert asyncio.run(mem.extract_and_store("", "md", "trip_1")) == 0


def test_extract_and_store_normal(monkeypatch):
    """正常流程：convert 返回两条偏好 -> upsert 被调两次 -> 返回 2。"""
    captured = []

    async def fake_convert(prompt, model):
        return '{"preferences": [{"category": "hotel", "content": "安静"}, {"category": "dining", "content": "爱吃辣"}]}'

    async def fake_upsert(user_id, category, content, source_trip_id):
        captured.append((user_id, category, content, source_trip_id))

    monkeypatch.setattr(mem, "convert_to_model", fake_convert)
    monkeypatch.setattr(mem, "upsert", fake_upsert)

    n = asyncio.run(mem.extract_and_store("user_1", "md", "trip_1"))

    assert n == 2
    assert ("user_1", "hotel", "安静", "trip_1") in captured
    assert ("user_1", "dining", "爱吃辣", "trip_1") in captured


def test_extract_and_store_conversion_failure(monkeypatch):
    """转换失败（LLM 抽风）：只返回 0，绝不抛异常 —— 记忆不能拖垮主流程。"""
    upsert_called = []

    async def fake_convert(prompt, model):
        raise ValueError("bad json")

    async def fake_upsert(*args):
        upsert_called.append(args)

    monkeypatch.setattr(mem, "convert_to_model", fake_convert)
    monkeypatch.setattr(mem, "upsert", fake_upsert)

    n = asyncio.run(mem.extract_and_store("user_1", "md", "trip_1"))

    assert n == 0
    assert upsert_called == []  # 失败时不写任何偏好
