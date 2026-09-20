"""在后端容器内初始化、签发、轮换及停用外部业务凭证。"""

import argparse
import json

from sqlalchemy.exc import SQLAlchemyError

from db_model.external_api_client import ExternalAPIClient
from infra.mysql import get_engine
from service.external_api_client import disable_client, issue_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="仅创建外部调用方表，已存在时不修改")
    for name in ("create", "rotate", "disable"):
        command = commands.add_parser(name)
        command.add_argument("--client-id", required=True)
        if name == "create":
            command.add_argument("--business-name", required=True)
        if name != "disable":
            command.add_argument("--expires-days", type=int, default=90)
    args = parser.parse_args()
    try:
        if args.command == "init":
            ExternalAPIClient.__table__.create(get_engine(), checkfirst=True)
            print("外部调用方表已就绪")
        elif args.command == "disable":
            disable_client(args.client_id)
            print("调用方已停用")
        else:
            key = issue_key(
                args.client_id,
                business_name=getattr(args, "business_name", None),
                expires_days=args.expires_days,
            )
            print("密钥仅展示本次，请通过安全渠道交付业务方；不要将输出保存到共享日志。")
            print(json.dumps({"client_id": args.client_id, "api_key": key}))
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    except SQLAlchemyError:
        parser.exit(1, "数据库操作失败，请检查连接、权限及表是否初始化。\n")


if __name__ == "__main__":
    main()
