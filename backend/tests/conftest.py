"""pytest 的公共配置。

这个文件只干两件事，都是为了让测试能顺利 import 到项目代码：

1. 把 backend 目录塞进 Python 的模块搜索路径（sys.path）。
   不加这两行的话，测试里写 `from services.plan_service import ...`
   会报 ModuleNotFoundError: No module named 'services'
   —— 和你之前跑 demo 时遇到的是同一个坑。

2. 加载 .env。测试的这几个函数其实用不到密钥，
   但 import services.plan_service 会连带 import 一整条链（agents / config.llm），
   里面会读环境变量，所以顺手加载一下更稳。

pytest 会自动加载 conftest.py，不需要你手动 import。
"""

import sys
from pathlib import Path

# __file__ 是 .../backend/tests/conftest.py
# .parent       -> .../backend/tests
# .parent.parent -> .../backend
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402  (必须在 sys.path 调整之后)

load_dotenv(BACKEND_DIR / ".env")
