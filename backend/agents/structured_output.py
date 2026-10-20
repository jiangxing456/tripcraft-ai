"""偏好抽取等已有调用共用的结构化输出入口。"""

import json
from pydantic import BaseModel
from config.llm import get_model


async def convert_to_model(input_text: str, target_model: type[BaseModel]) -> str:
    schema = json.dumps(target_model.model_json_schema(), ensure_ascii=False)
    model = get_model().with_structured_output(target_model, method="json_mode")
    messages = [
        ("system", "只返回符合以下 schema 的 JSON，不补造原文没有的事实：" + schema),
        ("user", input_text),
    ]
    result = await model.ainvoke(messages)
    if result is None:
        raise ValueError("模型没有返回结构化结果")
    return result.model_dump_json()
