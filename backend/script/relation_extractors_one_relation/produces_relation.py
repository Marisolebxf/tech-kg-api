"""One-relation extractor: PRODUCES（Organization → Product）.

复刻旧 organization_relation_etl.py 口径：国内外机构经营信息表，Product 端为规范化产品名 md5。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。
"""

from script.relation_extractors_one_relation.org_edges import org_relation_cli


def main() -> None:
    org_relation_cli("product")


if __name__ == "__main__":
    main()
