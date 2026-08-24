"""One-relation extractor: SHAREHOLDER_OF（Person|Organization → Organization）.

复刻旧 organization_relation_etl.py 口径：国内股东按 owners_type 分流人/机构端，海外股东要求精确唯一名解析。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。
"""

from script.relation_extractors_one_relation.org_edges import org_relation_cli


def main() -> None:
    org_relation_cli("shareholder")


if __name__ == "__main__":
    main()
