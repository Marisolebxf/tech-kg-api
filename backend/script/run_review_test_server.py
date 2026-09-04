"""人工处理前后端联调测试服务器。

用 sqlite 覆盖 production service 单例、mock 重跑、关闭网关签名校验，
在指定端口启动真实 uvicorn，供前端 vitest 用真实 axios 函数经 HTTP 联调。

仅用于测试，不要在生产部署。启动：
    uv run python script/run_review_test_server.py --port 18099
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

# 在导入 main 之前配置环境，避免触碰真实 MySQL/共享 sqlite
# 默认 real：dispatch_resume 走真实 HTTP 到图谱构建替身（run_graph_build_double），
# 避免任何 mock 重跑数据。可用 --rerun-mode mock 退回 mock（仅对照）。
os.environ.setdefault("REVIEW_RERUN_MODE", "real")
os.environ.setdefault("REVIEW_IDENTITY_REQUIRE_SIGNATURE", "false")
os.environ.setdefault("GRAPH_BUILD_SERVICE_TOKEN", "test-service-token")
os.environ.setdefault("REVIEW_PRODUCTION_ENABLED", "true")
os.environ.setdefault("REVIEW_SNAPSHOT_MAX_BYTES", "2097152")
os.environ.setdefault("REVIEW_RESUME_MAX_ATTEMPTS", "5")
# Legacy review endpoint integration cases exercise the repository's built-in
# deterministic fixtures. Production keeps this disabled by default.
os.environ.setdefault("WORKFLOW_DEMO_DATA_ENABLED", "true")
# workflow sqlite 落到临时文件，避免多人共用 /tmp 只读库
os.environ.setdefault(
    "WORKFLOW_DATABASE_PATH",
    str(Path(tempfile.gettempdir()) / f"tech-kg-workflows-review-server-{os.getpid()}.db"),
)
# 算子目录指到临时空目录，避免 watcher/初始化触碰真实算子
_op_dir = Path(tempfile.gettempdir()) / f"tech-kg-operators-{os.getpid()}"
_op_dir.mkdir(exist_ok=True)
os.environ.setdefault("OPERATOR_DIR", str(_op_dir))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from biz.handler import manual_review as public_handler  # noqa: E402
from biz.handler import manual_review_internal as internal_handler  # noqa: E402
from db_model.base import Base  # noqa: E402
from service.manual_review_production import ManualReviewService  # noqa: E402


def _build_sqlite_service() -> ManualReviewService:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--graph-build-url",
        default=os.getenv("GRAPH_BUILD_INTERNAL_URL", ""),
        help="图谱构建替身地址；real 模式下 dispatch_resume 真实调用之",
    )
    parser.add_argument(
        "--rerun-mode",
        default=os.environ.get("REVIEW_RERUN_MODE", "real"),
        choices=["real", "mock"],
    )
    args = parser.parse_args()

    os.environ["REVIEW_RERUN_MODE"] = args.rerun_mode
    if args.graph_build_url:
        os.environ["GRAPH_BUILD_INTERNAL_URL"] = args.graph_build_url.rstrip("/")

    # 用 sqlite 服务覆盖 handler 持有的两个单例引用
    svc = _build_sqlite_service()
    public_handler.production_service = svc
    internal_handler.manual_review_service = svc

    import uvicorn  # noqa: E402

    from main import app  # noqa: E402

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
