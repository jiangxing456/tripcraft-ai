"""
统一的 LLM 配置 —— 全项目的 Agent 共用这一个模型实例。

想换模型，只改这个文件就够了：
    本地 Ollama  →  DeepSeek(id="qwen2.5:3b") / Ollama(id="qwen2.5:3b")
    云端 DeepSeek →  DeepSeek(id="deepseek-flash")   ← 当前使用
"""

from pathlib import Path

from agno.models.deepseek import DeepSeek
from dotenv import load_dotenv

# 本文件位于 backend/config/，parents[1] 即 backend/，
# 这样不管从哪个目录启动，都能正确读到 backend/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# deepseek-flash 即 DeepSeek-V4.1-Flash，走官方 OpenAI 兼容接口。
# 密钥自动从环境变量 DEEPSEEK_API_KEY 读取，不硬编码在代码里。
model = DeepSeek(id="deepseek-flash")
