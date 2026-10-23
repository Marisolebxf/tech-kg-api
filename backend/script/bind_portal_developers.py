"""核对并绑定门户开发人员与本地业务；默认只读，--apply 才写入，不修改图空间。"""

import argparse
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.auth import AuthSettings
from db_model.business_access import (
    BusinessClient,
    BusinessMember,
    BusinessMembership,
    BusinessMembershipState,
)
from db_model.platform_governance import PlatformUser, PlatformUserRole
from infra.user_center import UserCenterClient
from service.platform_access import ADMIN_ROLE, PORTAL_ROLE_SNAPSHOT


def bind(session: Session, plan: dict, settings: AuthSettings, *, apply: bool = False) -> dict:
    if not settings.enabled or not settings.portal_developer_role_codes:
        raise ValueError("请启用真实认证并配置 USER_CENTER_PORTAL_DEVELOPER_ROLE_CODES")
    if (
        not isinstance(plan, dict)
        or not {"businesses", "members"} <= set(plan)
        or set(plan) - {"businesses", "members", "userCenterOpenApiBaseUrl"}
    ):
        raise ValueError("计划需要 businesses、members，可选 userCenterOpenApiBaseUrl")
    if "userCenterOpenApiBaseUrl" in plan:
        expected = plan["userCenterOpenApiBaseUrl"]
        actual = settings.user_center_open_api_base_url or (
            f"{settings.user_center_base_url.split('/admin-api/', 1)[0]}/open-api/system"
        )
        if not isinstance(expected, str) or expected.rstrip("/") != actual.rstrip("/"):
            raise ValueError("计划与当前用户中心环境不一致，禁止跨环境绑定")
    businesses, members = plan["businesses"], plan["members"]
    if not isinstance(businesses, list) or not isinstance(members, list) or not members:
        raise ValueError("businesses 和 members 必须为列表，成员不能为空")
    business_ids = set()
    business_names = set()
    for business in businesses:
        if not isinstance(business, dict) or set(business) != {"clientId", "name"}:
            raise ValueError("业务需要 clientId 与 name")
        cid, name = business["clientId"], business["name"]
        if (
            not isinstance(cid, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", cid)
            or cid in business_ids
            or not isinstance(name, str)
            or not name.strip()
            or name in business_names
            or len(name) > 200
        ):
            raise ValueError("业务编号或名称无效/重复")
        business_ids.add(cid)
        business_names.add(name)
        existing = session.get(BusinessClient, cid)
        if existing and (not existing.enabled or existing.name != name):
            raise ValueError(f"业务 {cid} 已存在但名称不同或已停用，停止覆盖")
        same_name = session.scalar(select(BusinessClient).where(BusinessClient.name == name))
        if same_name and same_name.client_id != cid:
            raise ValueError(f"业务名称 {name} 已对应其他编号，请沿用现有编号")
    users = set()
    resolved_members = []
    for member in members:
        if not isinstance(member, dict) or set(member) not in (
            {"userId", "username", "clientId"},
            {"username", "clientId"},
        ):
            raise ValueError("成员需要 username 和 clientId，userId 可选")
        username = member["username"]
        if not isinstance(username, str) or not username.strip():
            raise ValueError("成员账号不能为空")
        if "userId" in member:
            uid = member["userId"]
            if not isinstance(uid, str) or not uid:
                raise ValueError("用户编号无效")
            user = session.get(PlatformUser, uid)
        else:
            matches = list(
                session.scalars(select(PlatformUser).where(PlatformUser.username == username))
            )
            # MySQL 可能使用不区分大小写的排序规则，仍按完整账号精确匹配。
            matches = [user for user in matches if user.username == username]
            if len(matches) != 1:
                raise ValueError("目标实例必须存在唯一的完整账号，请先登录子系统并核对账号")
            user = matches[0]
            uid = user.user_id
        if not isinstance(uid, str) or not uid or uid in users:
            raise ValueError("用户编号无效/重复")
        users.add(uid)
        if not user or user.username != member["username"]:
            raise ValueError(f"用户 {uid} 与计划账号不一致，请先在目标实例登录核验")
        if member["clientId"] not in business_ids:
            raise ValueError("成员业务不在计划中")
        if uid in settings.initial_admin_user_ids or session.scalar(
            select(PlatformUserRole.id).where(
                PlatformUserRole.user_id == uid,
                PlatformUserRole.role_code.in_((ADMIN_ROLE, PORTAL_ROLE_SNAPSHOT)),
            )
        ):
            raise ValueError(f"用户 {uid} 已有管理员授权，本工具不隐式降级")
        if uid in settings.business_only_user_ids:
            raise ValueError(f"用户 {uid} 为业务专用账号，不能开放开发权限")
        # 连停用业务和尚未启用的新表记录也核对，避免启用覆盖标记时激活隐藏授权。
        bound = set(
            session.scalars(
                select(BusinessMembership.client_id).where(BusinessMembership.user_id == uid)
            )
        )
        if session.get(BusinessMembershipState, uid) is None:
            legacy = session.get(BusinessMember, uid)
            if legacy:
                bound.add(legacy.client_id)
        if bound - {member["clientId"]}:
            raise ValueError(f"用户 {uid} 已绑定其他业务，本工具不隐式转移")
        resolved_members.append({**member, "userId": uid})
    # 使用部署实例的签名凭据验证门户角色；接口不兼容或角色未授权时不写任何记录。
    client = UserCenterClient(settings)
    portal_users = set()
    for code in settings.portal_developer_role_codes:
        portal_users.update(client.role_user_ids(code))
    missing = users - portal_users
    if missing:
        raise ValueError(f"以下用户尚无门户开发人员角色：{', '.join(sorted(missing))}")
    if apply:
        for business in businesses:
            if session.get(BusinessClient, business["clientId"]) is None:
                session.add(BusinessClient(client_id=business["clientId"], name=business["name"]))
        session.flush()
        for member in resolved_members:
            uid, cid = member["userId"], member["clientId"]
            if session.get(BusinessMembershipState, uid) is None:
                session.add(BusinessMembershipState(user_id=uid))
            row = session.get(BusinessMembership, (uid, cid))
            if row is None:
                session.add(BusinessMembership(user_id=uid, client_id=cid, role="developer"))
            else:
                row.role = "developer"
    return {
        "applied": apply,
        "businesses": businesses,
        "members": resolved_members,
        "graphSpacesChanged": False,
        "legacyMembershipsChanged": False,
    }


def main():
    from infra.mysql import get_engine

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with open(args.plan, encoding="utf-8-sig") as stream:
        plan = json.load(stream)
    with Session(get_engine()) as session, session.begin():
        report = bind(session, plan, AuthSettings.from_env(), apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
