"""在 dev2 平台面创建目标图空间（真实 CREATE SPACE + 归属/说明/向量库登记）。

走 GraphSpaceService.create_space 服务层（与页面"新建图空间"同一条路径），
actor=2672（platform_admin）。CREATE SPACE 后轮询 SHOW SPACES 等待 schema 传播。

用法（api 容器内）::

    PYTHONPATH=/app /app/.venv/bin/python -m script.gkx_kg_small_build.create_space \
        [--space gkx_kg_sm] [--description "..."]
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("create_small_space")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", default="gkx_kg_sm")
    parser.add_argument("--description", default="gkx_kg 少量真实样例·全流程建图演示（20261027）")
    args = parser.parse_args()

    from infra.mysql import session_scope
    from service.graph_space import GraphSpaceService
    from service.platform_access import PlatformActor

    actor = PlatformActor(
        user_id="2672", username="19941138056", display_name="19941138056",
        email="", is_admin=True,
    )
    with session_scope() as session:
        service = GraphSpaceService(session)
        result = service.create_space(actor, args.space, args.description)
    logger.info("图空间创建结果: %s", result)


if __name__ == "__main__":
    main()
