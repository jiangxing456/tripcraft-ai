"""只从用户明确请求抽取偏好，规划前读取并注入。"""

from typing import List

from pydantic import BaseModel, Field
from loguru import logger

from agents.structured_output import convert_to_model
from repository.user_preference_repository import list_by_user, upsert


class PreferenceItem(BaseModel):
    category: str = Field(
        description="偏好维度：hotel / dining / pace / budget / transport / general"
    )
    content: str = Field(description="一句话描述该偏好，如「偏好安静、靠近地铁的酒店」")


class UserPreferences(BaseModel):
    preferences: List[PreferenceItem] = Field(default_factory=list)


_CATEGORY_LABEL = {
    "hotel": "酒店",
    "dining": "美食",
    "pace": "节奏",
    "budget": "预算",
    "transport": "交通",
    "general": "其他",
}


async def extract_and_store(
    user_id: str, travel_request_md: str, trip_plan_id: str
) -> int:
    """从用户本次明确请求抽取用户长期偏好并入库，返回写了几条。

    抽取失败只打日志、返回 0，绝不影响主流程（主流程不能因为记忆挂了而失败）。
    """
    if not user_id:
        return 0

    prompt = (
        "从下面一次旅行规划中提取用户的长期偏好（酒店/美食/节奏/预算/交通/其他）。\n"
        "只提取用户明确表达或强烈暗示的偏好，不要臆造；没有就返回空列表。\n\n"
        f"用户请求：\n{travel_request_md}"
    )

    try:
        # 复用结构化输出工具：让模型按 UserPreferences schema 返回 JSON
        json_str = await convert_to_model(prompt, UserPreferences)
        data = UserPreferences.model_validate_json(json_str)
    except Exception as e:
        logger.warning(f"偏好提取失败（不影响主流程）: {e}")
        return 0

    count = 0
    for item in data.preferences:
        if not item.content or not item.category:
            continue
        await upsert(user_id, item.category, item.content, trip_plan_id)
        count += 1
    return count


async def build_context(user_id: str) -> str:
    """查该用户全部偏好，拼成注入 prompt 的 markdown 片段；无偏好返回空串。"""
    if not user_id:
        return ""
    prefs = await list_by_user(user_id)
    if not prefs:
        return ""
    lines = ["## 用户的长期偏好（来自历史旅行，仅供参考）"]
    for p in prefs:
        label = _CATEGORY_LABEL.get(p.category, p.category)
        lines.append(f"- {label}: {p.content}")
    return "\n".join(lines)
