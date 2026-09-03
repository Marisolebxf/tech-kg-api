# 使用 Python 3.11.13 slim 镜像
FROM python:3.11.13-slim

# 设置工作目录
WORKDIR /app

# Docker 构建默认使用阿里云 PyPI 镜像，可通过 build arg 覆盖。
ARG PYPI_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=${PYPI_INDEX_URL} \
    UV_DEFAULT_INDEX=${PYPI_INDEX_URL} \
    PYTHONDONTWRITEBYTECODE=1 \
    TECH_KG_STATE_DIR=/var/lib/tech-kg

# pip 安装 uv 和 uv 同步项目依赖均使用上述镜像。
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

# 仅复制运行所需代码，防止测试数据、凭据文件或构建上下文意外进入镜像。
COPY application ./application
COPY biz ./biz
COPY config ./config
COPY dao ./dao
COPY db_model ./db_model
COPY idl ./idl
COPY infra ./infra
COPY middleware ./middleware
COPY operators ./operators
COPY organization_ETL ./organization_ETL
COPY schemas ./schemas
COPY script ./script
COPY service ./service
COPY static ./static
COPY utils ./utils
COPY main.py ./main.py

# 运行时只允许写入明确的状态目录，应用源码和虚拟环境保持 root 只读。
RUN mkdir -p /app/operators/user /app/var/patent_indexes /var/lib/tech-kg \
    && chown -R app:app /app/operators/user /app/var /var/lib/tech-kg

USER app

# 暴露端口
EXPOSE 8000

# 启动命令（直接用 venv 的 uvicorn，避免 uv run 在容器启动时重新同步依赖）
CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
