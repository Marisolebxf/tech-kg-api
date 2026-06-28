"""统一响应包装模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一响应：{code, success, data, msg}。

    code 为业务状态码（200 成功，其余失败）；data 承载业务结果对象；
    success 与 code 同义；msg 为提示消息。
    """

    code: int = 200
    success: bool = True
    data: Any = None
    msg: str = "success"
