"""延迟创建模型：演示和单元测试不需要 API 密钥。"""

import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_model():
    return ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        # DeepSeek 思考模式不支持结构化输出所需的指定 tool_choice。
        extra_body={"thinking": {"type": "disabled"}},
        temperature=0,
        timeout=60,
        max_retries=2,
    )
