"""仅用于安全校验测试；禁止执行。"""


def transform(row):
    """通过无终止条件的递归持续扩张输入，最终耗尽进程资源。"""
    expanded = {"original": row, "duplicate": [row, row]}
    return transform(expanded)
