"""python main.py --demo；真实查询：python main.py。"""

import argparse
import os
from pathlib import Path
from dotenv import load_dotenv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TripCraft LangGraph")
    parser.add_argument(
        "--demo", action="store_true", help="固定数据演示，不调用 LLM/真实旅行数据"
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    load_dotenv(Path(__file__).with_name(".env"))
    if args.demo:
        os.environ["TRIPCRAFT_DEMO"] = "1"
    import uvicorn

    uvicorn.run("api.app:app", host="127.0.0.1", port=args.port)
