# tech-kg-api

亿级知识图谱 API 接口仓库

## 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Marisolebxf/tech-kg-api.git
cd tech-kg-api
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 启动服务

```bash
uv run uvicorn app.main:app --reload
```

启动后访问：

- <http://localhost:8000/hello>
- <http://localhost:8000/api>
- <http://localhost:8000/docs> （自动生成的接口文档）

## 运行测试

```bash
uv run pytest
```

## 项目结构

```
tech-kg-api/
  ├── app/
  │   ├── __init__.py
  │   └── main.py          # FastAPI 主入口
  ├── tests/
  │   ├── __init__.py
  │   └── test_main.py     # 测试文件
  ├── .github/
  │   └── workflows/
  │       └── ci.yml       # GitHub Actions CI/CD
  ├── pyproject.toml
  └── README.md
```