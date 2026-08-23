# 使用 Python 3.11.13 slim 镜像
FROM python:3.11.13-slim

# 设置工作目录
WORKDIR /app

# Docker 构建默认使用阿里云 PyPI 镜像，可通过 build arg 覆盖。
ARG PYPI_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=${PYPI_INDEX_URL} \
    UV_DEFAULT_INDEX=${PYPI_INDEX_URL}

# pip 安装 uv 和 uv 同步项目依赖均使用上述镜像。
RUN pip install --no-cache-dir uv

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
