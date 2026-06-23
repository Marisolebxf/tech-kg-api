# 使用 Python 3.11.13 slim 镜像
FROM python:3.11.13-slim

# 设置工作目录
WORKDIR /app

# 安装 uv（默认 PyPI；如需国内镜像可改 -i https://pypi.tuna.tsinghua.edu.cn/simple）
RUN pip install uv

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev 

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令（直接用 venv 的 uvicorn，避免 uv run 在容器启动时重新同步依赖）
CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
