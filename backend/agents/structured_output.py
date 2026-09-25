"""
结构化输出工具：把 Agent 产出的自由文本（旅行调研 Markdown）转成
符合指定 Pydantic 模型 schema 的 JSON 字符串。

为什么这么短？
    早期用本地小模型（qwen2.5:3b）时它经常不肯好好输出 JSON，所以写了三层手工兜底；
    换成 DeepSeek 之后，Agno 自带的 output_schema 就能稳定拿到结构化结果，
    因此这里只保留最必要的三步：
        正常调用一次 → 失败就换个更严格的提示词重试 → 再失败才抛错。
"""

import json
import re#正则
from typing import Type, TypeVar

from agno.agent import Agent
from loguru import logger
from pydantic import BaseModel, ValidationError

from config.llm import model

# 泛型 T：限定必须是 Pydantic 模型（BaseModel 的子类）
T = TypeVar("T", bound=BaseModel)

# 三次尝试分别追加的提示词（第一次为空，表示用正常语气）
_RETRY_HINTS = [
    "",
    "Previous attempt was invalid. Return ONLY minified JSON matching the schema.",
    "Return ONLY a minified JSON object. First character must be '{'. Last character must be '}'.",
]


def _extract_json(text: str) -> str:
    """从模型回复里抠出JSON ： 先剥掉 markdown 代码围栏，再退化为「最大花括号块」。"""
    text = (text or "").strip()

    # 模型最爱干的事：把 JSON 包在 ```json ... ``` 里，取最后一个围栏的内容
    fenced = re.findall(#找出所有匹配正则的地方，返回列表
        r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE#re.DOTALL:匹配换行符.re.IGNORECASE:忽略大小写
    )
    if fenced:
        text = fenced[-1].strip()

    # 退一步：截取从第一个 '{' 到最后一个 '}' 的片段
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text#切片左闭右开


def _build_prompt(input_text: str, target_model: Type[T], retry_hint: str = "") -> str:
    """拼装提示词：目标结构 schema + 输出规则 + 待转换的原文。"""
    schema_str = json.dumps(target_model.model_json_schema(), indent=2)#第三方 pydantic】方法，拿到这个模型的 JSON Schema（就是字段和那些 `Field(description)`）
    return f"""
Convert the travel research below into ONE valid JSON object that matches the schema.
Return ONLY JSON. No markdown. No explanations. No code fences.

Schema:
{schema_str}

Rules:
- Output must be valid JSON object
- Include all required fields
- Use empty strings/lists when a value is missing
- Keep string values concise
- Do not invent unrelated destinations

{retry_hint}

Travel research:
{input_text}
""".strip()


def _build_agent(target_model: Type[T]) -> Agent:
    """创建一个一次性的「转换器」Agent。

    用 output_schema 把目标模型交给 Agno，由框架负责约束模型输出并解析成对象,
    比靠提示词求模型守规矩可靠得多。
    """
    return Agent(
        model=model,
        description=(
            "You convert free-form travel research into a single valid JSON object "
            "matching a fixed schema. Never return prose."
        ),
        instructions=[
            "Return only a JSON object.",
            "No markdown fences.",
            "No preamble or closing text.",
            "If data is incomplete, fill with empty strings or empty lists.",
        ],
        markdown=False,
        output_schema=target_model,
        structured_outputs=True,
    )

#targe_model 是谁调用换成目标结构，plan_service.py调用了所以是TravelPlanTeamResponse
async def convert_to_model(input_text: str, target_model: Type[T]) -> str:
    """把 input_text 转成 target_model 对应的 JSON 字符串。

    带 3 次重试，全部失败抛 ValueError（调用方据此决定是否走兜底）。
    """
    logger.info(
        f"Converting to {target_model.__name__} ({len(input_text or '')} chars)"
    )

    last_error = None
    for attempt, retry_hint in enumerate(_RETRY_HINTS, start=1):
        try:
            # 每次重试都新建 Agent，避免上一轮的对话历史干扰本次输出
            agent = _build_agent(target_model)
            prompt = _build_prompt(input_text, target_model, retry_hint)
            response = await agent.arun(prompt)
            content = response.content

            # 最常见的情况：Agno 已按 schema 解析成了 Pydantic 对象，直接序列化
            if isinstance(content, BaseModel):
                return content.model_dump_json()

            # 兜底：拿到的是 dict 或字符串，自己解析 + 用 Pydantic 校验一遍
            data = content if isinstance(content, dict) else json.loads(_extract_json(str(content)))
            return target_model.model_validate(data).model_dump_json()

        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as err:
            # 可预期的失败：JSON 不合法 / 字段对不上 → 换提示词再试
            last_error = err
            logger.warning(f"Structured output attempt {attempt} failed: {err}")
        except Exception as err:
            # 网络抖动、接口报错等 → 同样重试，不直接崩掉
            last_error = err
            logger.warning(f"Structured output attempt {attempt} unexpected error: {err}")

    raise ValueError(
        f"Failed to parse response into {target_model.__name__}: {last_error}"
    )
