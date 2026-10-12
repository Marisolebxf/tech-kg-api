"""Check legacy public-default conflicts; create only the new empty preference table."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from sqlalchemy import inspect, select

from db_model.llm_config import LlmConfig
from db_model.llm_default import BusinessLlmDefault
from infra.mysql import create_session, get_engine
from service.llm_defaults import config_business, resolve_default_config


def check_defaults(session):
    rows = list(session.scalars(select(LlmConfig).where(LlmConfig.is_default.is_(True))))
    conflicts = []
    for row in rows:
        reasons = []
        if config_business(session, row.id):
            reasons.append("公共默认指向业务专属模型")
        if len(rows) > 1:
            reasons.append("存在多个公共默认")
        if row.status == "停用":
            reasons.append("公共默认已停用")
        if not row.api_key:
            reasons.append("公共默认缺少 API Key")
        if reasons:
            conflicts.append(
                {
                    "configId": row.id,
                    "businessId": config_business(session, row.id),
                    "reasons": reasons,
                }
            )
    if inspect(session.get_bind()).has_table(BusinessLlmDefault.__tablename__):
        for preference in session.scalars(select(BusinessLlmDefault)):
            try:
                resolve_default_config(session, preference.business_id, preference.config_id)
            except HTTPException as exc:
                conflicts.append(
                    {
                        "configId": preference.config_id,
                        "businessId": preference.business_id,
                        "reasons": [exc.detail],
                    }
                )
    return {"publicDefaultIds": [row.id for row in rows], "conflicts": conflicts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Create empty table only after conflict-free check"
    )
    args = parser.parse_args()
    with create_session() as session:
        report = check_defaults(session)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["conflicts"]:
        raise SystemExit("现有默认存在归属、数量或可用性冲突，未执行迁移；请先明确处理现有默认")
    if args.apply:
        BusinessLlmDefault.__table__.create(get_engine(), checkfirst=True)
        print("业务默认表就绪；原公共默认保持不变，各业务初始跟随公共默认")


if __name__ == "__main__":
    main()
