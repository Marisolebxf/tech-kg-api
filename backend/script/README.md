# Script

启动、维护、数据初始化等脚本放在此目录。

## 脚本清单

| 脚本 | 作用 | 说明 |
|---|---|---|
| `init_db.py` | 执行 `schemas/ddl/` 下全部 DDL | 会连接 `MYSQL_*` 指向的数据库并建表，执行前确认目标库不是只读源库 |
| `sync_schema_from_mysql.py` | 从 MySQL 同步 DDL、字段规范和 ORM | 只读取 `information_schema` 和 `SHOW CREATE TABLE`，不会修改源库数据 |

## 常用命令

同步远程 `gkx` schema：

```bash
MYSQL_HOST=183.240.141.251 \
MYSQL_PORT=3318 \
MYSQL_DATABASE=gkx \
MYSQL_USERNAME=gkx_reader_zp \
MYSQL_PASSWORD='***' \
uv run python script/sync_schema_from_mysql.py
```

在目标库执行建表：

```bash
MYSQL_HOST=target_host \
MYSQL_PORT=target_port \
MYSQL_DATABASE=target_database \
MYSQL_USERNAME=target_user \
MYSQL_PASSWORD='target_password' \
uv run python script/init_db.py
```
