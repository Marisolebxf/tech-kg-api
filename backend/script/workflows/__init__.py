"""工作流平台上传脚本封装层。

每个模块把现有 ETL 封装成 ``workflow(payload)`` 函数，供 ``kg.custom.python``
工作流在 Activity 子进程里调用。子进程由 ``execute_python_script`` 启动，已加载
backend/.env 并把 backend 目录加入 PYTHONPATH，故此处可直接 import infra/dao/script。
"""
