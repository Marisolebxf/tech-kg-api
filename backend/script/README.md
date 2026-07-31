# Script

启动、维护、数据初始化等脚本放在此目录。

## 脚本清单

| 脚本 | 作用 | 说明 |
|---|---|---|
| `init_db.py` | 执行 `schemas/ddl/` 下全部 DDL | 默认连接开发业务库 `127.0.0.1:3306/gkx_element` |
| `sync_schema_from_mysql.py` | 从源 MySQL 同步 DDL、字段规范和 ORM | 优先读取 `SOURCE_MYSQL_*`，只读 `information_schema` 和 `SHOW CREATE TABLE` |

## 常用命令

初始化已有的科技要素业务库 `gkx_element` 中由本项目维护的表：

目标数据库必须预先存在；脚本只执行 `schemas/ddl/` 下由本项目维护的建表 DDL，不负责创建数据库，也不创建专利厂商源表。

```bash
MYSQL_HOST=127.0.0.1 \
MYSQL_PORT=3306 \
MYSQL_DATABASE=gkx_element \
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
