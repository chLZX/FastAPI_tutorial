# Alembic 从零搭建指南（book_system 项目）

## 0. 前置条件

- 已经装好 `alembic`、`sqlmodel`（或 `sqlalchemy`）、对应的数据库驱动
- 项目用的是**异步引擎**（`AsyncEngine` + `asyncpg`），所以初始化时要用 Alembic 自带的 `async` 模板
- 项目里已经有 SQLModel/SQLAlchemy 的模型类，比如：
  - `book_system/model/main.py` 里的 `Book`
  - `book_system/auth/models.py` 里的 `User`

---

## 1. 初始化 Alembic（异步模板）

在项目根目录（能 `import book_system` 的那一层，也就是 `book_system/` 目录本身）执行：

```bash
cd /Users/lzxx/Desktop/pj/fastapi_tutorial/step5/src/book_system
alembic init -t async migrations
```

注意命令格式：`-t async` 是**模板选项**，`migrations` 是**目标目录名**。不能直接写成 `alembic init async migrations`（那样 Alembic 会把 `async` 当成目录名，`migrations` 当成多余的参数报错）。

`-t async` 和默认模板的区别：默认模板生成的 `env.py` 是同步引擎的代码，你得自己手动把它改成异步版本（见下面第 3.3 节）；用 `-t async` 生成的 `env.py` **已经内置了异步引擎所需的样板代码**（`asyncio.run`、`async_engine_from_config` 等），可以少改很多东西。

执行后会自动生成：

```
book_system/
├── alembic.ini              # Alembic 主配置文件
└── migrations/
    ├── env.py                # 迁移运行时的入口脚本（已经是异步模板，仍需接入项目配置和模型）
    ├── README                # 模板自带的说明（英文，写着 "async dbapi"）
    ├── script.py.mako        # 生成新迁移文件时用的模板
    └── versions/              # 以后每次生成的迁移文件都放这里（目前是空的）
```

> 目录名 `migrations` 可以随意改成别的（比如 `alembic`），但要和后面 `alembic.ini` 里的 `script_location` 保持一致。

---

## 2. 改 `alembic.ini`

`alembic init` 生成的是一份"通用模板"，重点看这两行：

```ini
[alembic]
script_location = %(here)s/migrations

...

sqlalchemy.url = driver://user:pass@localhost/dbname
```

- `script_location`：指向刚才生成的 `migrations` 目录，一般不用改。
- `sqlalchemy.url`：这里写的是**占位符**。如果你打算用 `.env` 里的 `DATABASE_URL`（通过 `Config.DATABASE_URL`），这一行可以不填真实值，因为会在 `env.py` 里用代码覆盖它（见下面）。

其他配置（`[loggers]`、`[post_write_hooks]` 等）保持默认即可，新手阶段不用动。

---

## 3. 改 `migrations/env.py`

用 `-t async` 生成的 `env.py` 已经带好了异步引擎的骨架，但**还需要你手动接入项目自己的配置和模型**，不然它不知道连哪个数据库、要管理哪些表。

### 3.1 导入配置，把数据库地址接进来

```python
from book_system.config import Config

config = context.config
config.set_main_option("sqlalchemy.url", Config.DATABASE_URL)
```

### 3.2 导入所有模型，让 Alembic "看得到"表

新手最容易踩的坑：**只有真正被 `import` 过的模型，才会注册进 `metadata`**。

```python
from book_system.auth.models import User
from book_system.model.main import Book
from sqlmodel import SQLModel

target_metadata = SQLModel.metadata
```

原理：`SQLModel.metadata` 是个全局注册表，模型类只要被 Python 执行过一次（即被 import 过）就会自动注册进去。如果忘了在 `env.py` 里 import 某个模型（比如新加了 `Order` 表），`alembic revision --autogenerate` 会完全检测不到这张表。

### 3.3 异步引擎的运行逻辑（`-t async` 模板已经帮你写好）

```python
async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())
```

这一段你基本不用动，`-t async` 模板已经生成好了；只需要确认 3.1、3.2 两处项目相关的接入代码加上了。

---

## 4. 日常工作流命令

### 4.1 每次改完模型（加字段、加表、改类型）之后

```bash
alembic revision --autogenerate -m "简短描述这次改了什么"
```

- 自动对比"当前数据库结构" vs "你的模型定义"
- 在 `migrations/versions/` 下生成一个新文件
- **一定要打开这个文件人工检查一遍**，autogenerate 不是 100% 准确（索引、默认值、枚举类型经常检测不全；字段类型变更有时需要手动加 `USING` 子句）

### 4.2 应用迁移到数据库

```bash
alembic upgrade head        # 升级到最新版本
alembic upgrade +1          # 从当前位置只往前走一步
alembic upgrade <revision>  # 升级到指定版本
```

### 4.3 回退

```bash
alembic downgrade -1         # 回退一步
alembic downgrade base       # 回退到最初
```

### 4.4 查看状态

```bash
alembic current    # 当前数据库在哪个版本
alembic history    # 看所有迁移的历史链条
alembic heads      # 看当前有几个"头"（正常应该只有一个）
```

---

## 5. 常见问题（FAQ）

### Q1：改了模型，`autogenerate` 却检测不到新表/新字段
**原因**：模型类没有被 `env.py` import 到，没注册进 `SQLModel.metadata`。
**解决**：确认 `env.py` 里显式 `import` 了所有模型模块。

### Q2：`column "xxx" cannot be cast automatically to type xxx`
**原因**：改字段类型时（比如 `VARCHAR → Date`），Postgres 不知道怎么转换已有数据。
**解决**：在 `op.alter_column(...)` 里加 `postgresql_using='列名::目标类型'`：

```python
op.alter_column('books', 'published_date',
    existing_type=sa.VARCHAR(),
    type_=sa.Date(),
    postgresql_using='published_date::date')
```

### Q3：往已有数据的表里加 `NOT NULL` 字段报错
**原因**：新列没有默认值，已有的行没法自动填值。
**解决**：
- 方案 1：加 `server_default=...`，让旧数据统一填一个默认值；
- 方案 2：分三步——先加可空列 → 手动/脚本 `UPDATE` 回填真实数据 → 再 `alter_column` 改成 `nullable=False`。

### Q4：`Multiple heads` / `Target database is not up to date`
**原因**：多人协作时，两个人各自基于同一个旧版本生成了不同的迁移文件，形成了两条分支。
**解决**：

```bash
alembic merge heads -m "merge"
```

### Q5：第一次 `autogenerate` 生成的 "init" 迁移里，出现了很多"意料之外"的改动
**原因**：如果表是在引入 Alembic 之前，靠 `SQLModel.metadata.create_all()` 直接建的，数据库里的实际结构可能和"现在的模型代码"已经不一致。Alembic 是拿"数据库现状" vs "当前模型"做 diff，不管是不是第一个迁移文件，历史遗留的不一致都会被检测出来。
**解决**：生成后打开文件人工核对，删掉不是本次想做的改动，或确认无误后保留。

### Q6：迁移执行到一半失败了，数据库会变成"半成品"状态吗？
**不会**，只要日志里有 `Will assume transactional DDL`，整个迁移包在一个事务里，中途报错会整体回滚。（Postgres 支持事务性 DDL；MySQL 不支持，需格外小心。）

### Q7：`downgrade()` 报错，是不是"回不去了"？
**原因**：`downgrade` 只改结构，不保证数据完整还原。
**建议**：`downgrade` 主要用于开发阶段撤销"跑错的迁移"，生产环境一般不依赖它回滚，出问题优先写新的"修复迁移"往前走。

### Q8：`sqlalchemy.url` 要不要写在 `alembic.ini` 里？
**看 `env.py`**：如果像本项目这样用 `config.set_main_option("sqlalchemy.url", Config.DATABASE_URL)` 动态覆盖了，`alembic.ini` 里那行占位符写不写都无所谓，不会被实际用到。
