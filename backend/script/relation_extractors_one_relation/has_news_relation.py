"""One-relation extractor: HAS_NEWS（Organization → News）.

复刻旧 organization_relation_etl.py 口径：机构重点资讯表，News 端 VID 含表名 + 整行哈希稳定键。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。
"""

from script.relation_extractors_one_relation.org_edges import org_relation_cli


def main() -> None:
    org_relation_cli("news")


if __name__ == "__main__":
    main()
