# Script

启动、维护、数据初始化等脚本放在此目录。

## 脚本清单

| 脚本 | 作用 | 说明 |
|---|---|---|
| `init_db.py` | 执行 `schemas/ddl/` 下全部 DDL | 默认连接实验室/本地 Docker MySQL `127.0.0.1:3306/gkx_local` |
| `sync_schema_from_mysql.py` | 从源 MySQL 同步 DDL、字段规范和 ORM | 优先读取 `SOURCE_MYSQL_*`，只读 `information_schema` 和 `SHOW CREATE TABLE` |

## 常用命令

初始化实验室副本库 `gkx_local`：

```bash
MYSQL_HOST=127.0.0.1 \
MYSQL_PORT=3306 \
MYSQL_DATABASE=gkx_local \
MYSQL_USERNAME=root \
MYSQL_PASSWORD=123456789 \
uv run python script/init_db.py
```

同步远程 `gkx` schema：

```bash
SOURCE_MYSQL_HOST=183.240.141.251 \
SOURCE_MYSQL_PORT=3318 \
SOURCE_MYSQL_DATABASE=gkx \
SOURCE_MYSQL_USERNAME=gkx_reader_zp \
SOURCE_MYSQL_PASSWORD='***' \
uv run python script/sync_schema_from_mysql.py
```

在其他目标库执行建表：

```bash
MYSQL_HOST=target_host \
MYSQL_PORT=target_port \
MYSQL_DATABASE=target_database \
MYSQL_USERNAME=target_user \
MYSQL_PASSWORD='target_password' \
uv run python script/init_db.py
```
