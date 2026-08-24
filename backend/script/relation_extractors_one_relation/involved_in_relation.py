"""One-relation extractor: INVOLVED_IN（Organization → Event）.

复刻旧 organization_relation_etl.py 口径：17 张事件表，4 种 extractor（event 通用/破产当事人/破产管理人/招投标方）。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。
"""

from script.relation_extractors_one_relation.org_edges import org_relation_cli


def main() -> None:
    org_relation_cli("event")


if __name__ == "__main__":
    main()
