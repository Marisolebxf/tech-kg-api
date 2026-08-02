"""启动科技图谱 Temporal Worker。"""

from __future__ import annotations

import asyncio
import logging

from service.temporal_runtime import temporal_runtime

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(temporal_runtime.run_worker())
