"""One-relation extractor: LEGAL_REP_OF（Person → Organization）.

复刻旧 organization_relation_etl.py 口径：法定代表人边：机构基础/研究院/台湾企业 3 张表，person 端用实体侧统一公式。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。
"""

from script.relation_extractors_one_relation.org_edges import org_relation_cli


def main() -> None:
    org_relation_cli("legal_representative")


if __name__ == "__main__":
    main()
