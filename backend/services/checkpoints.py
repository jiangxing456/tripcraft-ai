"""在线程中用同步驱动，避免 Windows 的 MCP 子进程与 psycopg 异步循环冲突。"""

import asyncio
from langgraph.checkpoint.postgres import PostgresSaver


class PostgresCheckpoints(PostgresSaver):
    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(
            self.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config, writes, task_id, task_path=""):
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        def read_records():
            return list(self.list(config, filter=filter, before=before, limit=limit))

        records = await asyncio.to_thread(read_records)
        for item in records:
            yield item
