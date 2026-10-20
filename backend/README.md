# TripCraft 代码阅读与运行

## 先运行实例

在 backend 目录执行：

```powershell
uv sync
.venv/Scripts/python.exe main.py --demo --port 8060
```

打开 http://127.0.0.1:8060/demo 。不要求 PostgreSQL 或大模型密钥。Redis 默认连接 127.0.0.1:6379，连接失败时跳过缓存。

1. 保持三天、3000 CNY，点击开始规划。
2. 四个调研节点并行，通过 stdio 真实调用本地 MCP 服务，返回明确标注的固定样本。
3. 初次报价 4240，超过预算；仅重查酒店，再核算为 2540。
4. 点击确认方案，图从 interrupt 检查点恢复，状态变为 completed。
5. 将预算改为 1000 后再运行：最多修正两次，保留 needs_review，禁止确认。
6. 再运行相同需求，观察 Redis 命中；修改预算后点击重规划，可从暂停位置继续。

演示只替换数据和模型输出，不伪装成真实行情或真实 LLM 决策。演示检查点在内存，重启后清空；页面也会显示这一点。

## 只需先读这四个文件

| 文件 | 作用 |
|---|---|
| services/planner.py | 状态、费用模型、校验、图节点与边、执行资源 |
| tools/travel_mcp.py | MCP 服务：固定样本与真实数据查询共用工具契约 |
| router/planner.py | 启动、SSE、状态、检查点历史和人工确认接口 |
| static/planner.html | 无前端框架的可交互实例 |

图：四项调研并行 → compose → validate → 超预算时 repair_hotel → compose；通过或达到上限后 review 暂停，确认后结束。调整预算只重做酒店和行程阶段。

LangChain create_agent 在真实模式中处理 MCP 工具调用循环，限制递归轮数与超时；预算校验使用 Python Decimal，不由 LLM 自判。

## 真实模式

backend/.env 保留原密钥，另可设置以下值（不要提交 .env）：

```dotenv
DEEPSEEK_API_KEY=your_key
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
EXA_API_KEY=your_key
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tripcraft_ai
REDIS_URL=redis://127.0.0.1:6379/0
```

启动 PostgreSQL 并保留原业务表；新 LangGraph 检查点表由 PostgresCheckpoints.setup() 创建，不删除原行程。然后执行 `python main.py --port 8060`（不传 --demo）。

真实航班工具要求 IATA 机场代码。目的地、酒店、餐饮由 Exa 查询；模型缺少可靠数据时任务应失败，不能把无来源输出当作成功。外部报价不等同实时库存或可预订结果。币种转换、详细交通时间冲突检查尚未实现。

原 POST /api/plan/trigger 仍用于 Next.js 业务入口，自动执行并落库；它沿用自动完成行为，不启用人工确认。人工确认与 SSE 实例使用 /api/planner/*。新的实例不依赖 Next.js，未改造旧页面为 SSE。

PostgreSQL 检查点支持重建 Planner 后继续读取、恢复暂停任务。SSE 事件日志只在单进程内存，重启后可以查检查点，不能重放旧 SSE。停止时取消未结束任务；不是可靠任务队列，不应声称支持自动恢复进程崩溃中的任务。

## 验证

```powershell
.venv/Scripts/python.exe -m pytest tests -q
```

关键用例覆盖费用精度、人数/晚数、币种、日期、预算不可达、重规划上限、人工确认恢复、调整预算与缓存。保留用户偏好测试；已删除旧模板兜底及其过时测试，改为验证失败不覆盖原方案和偏好异常不推翻已完成结果。

## 技术来源

- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://reference.langchain.com/python/langgraph/checkpoints
- https://github.com/modelcontextprotocol/python-sdk

这是本机开发实例，不提供公网部署配置。

Windows 下 psycopg 异步驱动与 MCP 子进程需要不同事件循环，因此 services/checkpoints.py 在线程中调用标准 PostgresSaver。已验证 PostgreSQL 关闭连接后重建图并恢复确认。

前端验证：在 client 目录运行 `pnpm test`、`pnpm exec tsc --noEmit` 和 `pnpm lint`。行程接口从服务端会话取得身份，只查询或删除当前用户的数据。

旧入口已复用同一执行图与行程状态，删除重复的 plan_tasks Python 读写层；既有历史表不删除。并发重复提交返回 409。
