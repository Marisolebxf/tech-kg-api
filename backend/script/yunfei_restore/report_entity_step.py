"""Report 实体抽取步（@step 薄适配层，yunfei_test 空间还原专用）。

直接调用老一对一脚本模块的 ``transform(payload)``——抽取逻辑与旧脚本完全
一致（行 → 记录的映射、vid 公式、provenance 均复用老代码），本文件只按
新规范以 @step 声明入口，供平台喂数管道（kg.schema.extract）调度。
"""

from kg_sdk import step

from script.entity_extractors_one_entity import report_entity as legacy


@step
def emit(payload):
    return legacy.transform(payload)
