"""首次管理员初始化；默认只读，必须核对认证 ID 后显式 --apply。"""

import argparse
import json
from uuid import uuid4

from sqlalchemy import insert, select

from db_model.platform_governance import PlatformUser, PlatformUserRole


def bootstrap(engine, username, expected_id=None, apply=False):
    users = PlatformUser.__table__
    roles = PlatformUserRole.__table__
    with engine.begin() as connection:
        matches = (
            connection.execute(
                select(users.c.user_id, users.c.username).where(users.c.username == username)
            )
            .mappings()
            .all()
        )
        matches = [row for row in matches if row.username == username]
        if len(matches) != 1:
            raise ValueError(
                "登录名未唯一匹配已登记账号；请先登录并核实统一认证用户名，不猜测账号 ID"
            )
        user_id = matches[0].user_id
        if expected_id is not None and expected_id != user_id:
            raise ValueError("认证 ID 与预期不一致，未修改权限")
        exists = (
            connection.execute(
                select(roles.c.id).where(
                    roles.c.user_id == user_id, roles.c.role_code == "platform_admin"
                )
            ).first()
            is not None
        )
        if apply:
            if not expected_id:
                raise ValueError("执行写入必须提供已核实的 --expect-user-id")
            if not exists:
                connection.execute(
                    insert(roles).values(
                        id=str(uuid4()),
                        user_id=user_id,
                        role_code="platform_admin",
                        granted_by="deployment:bootstrap_business_admin",
                    )
                )
        return {
            "username": username,
            "userId": user_id,
            "isLocalAdmin": exists or apply,
            "changed": apply and not exists,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--expect-user-id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from infra.mysql import get_engine

    try:
        result = bootstrap(get_engine(), args.username, args.expect_user_id, args.apply)
    except ValueError as exc:
        print(str(exc))
        return 2
    except Exception as exc:
        # 数据库异常可能包含连接信息，不回显原始异常。
        print(f"初始化失败（{type(exc).__name__}），请检查数据库连接、表结构及并发操作")
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
