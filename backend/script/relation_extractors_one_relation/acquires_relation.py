"""One-relation extractor: ACQUIRES（Organization → Organization）.

复刻旧 organization_relation_etl.py 口径：并购事件表，边属性金额/币种。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。
"""

from script.relation_extractors_one_relation.org_edges import org_relation_cli


def main() -> None:
    org_relation_cli("acquisition")


if __name__ == "__main__":
    main()
