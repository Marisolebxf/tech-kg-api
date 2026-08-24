"""One-relation extractor: SUBSIDIARY_OF（子公司 → 母公司）.

复刻旧 organization_relation_etl.py 口径：海外子公司表，母公司需稳定 ID 或精确唯一名。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。
"""

from script.relation_extractors_one_relation.org_edges import org_relation_cli


def main() -> None:
    org_relation_cli("subsidiary")


if __name__ == "__main__":
    main()
