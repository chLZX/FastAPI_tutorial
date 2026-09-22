# Bookly（step2）代码笔记

记录 `book_system` 这套代码里几个关键设计的原理："为什么这么写"，而不只是"这是什么"。

---

## 1. `db/main.py` —— 引擎怎么建、表怎么建

```python
from sqlmodel import SQLModel, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from book_system.config import config

engine = AsyncEngine(create_engine(
    url=config.DATABASE_URL,
    echo=True
))

async def init_db():
    async with engine.begin() as conn:
        from book_system.model.main import Book
        await conn.run_sync(SQLModel.metadata.create_all)
```

### `create_engine` + `AsyncEngine`：造一个"异步版"的数据库引擎

`create_engine(...)` 本来是 SQLAlchemy **同步**版的引擎构造函数。`AsyncEngine(...)` 把它包了一层，让它具备异步能力——本质上等价于官方推荐的 `create_async_engine(url=..., echo=True)`，只是手动拼出来的写法，前提是 `DATABASE_URL` 里必须用异步驱动（`postgresql+asyncpg://...`），否则包了也没用。

`echo=True` 是调试开关：打开后每一条真实执行的 SQL 都会打印到终端，方便排查问题；上线前应该关掉（`echo=False`），否则日志会被刷爆，还可能把敏感数据打印出来。

### `conn.run_sync(SQLModel.metadata.create_all)`：把"表的定义"真正建到数据库里

这一行要拆成两半理解：

- **`SQLModel.metadata`** 是一个全局"花名册"，只要某个 `SQLModel` 表模型类（比如 `Book`）被 Python **import 过一次**，它就会自动登记进这个花名册——**这一步只是 Python 内部的记账，不碰数据库**。这也是为什么 `from book_system.model.main import Book` 要写在函数**内部**：一是确保调用 `create_all` 之前 `Book` 已经被登记，二是避免和 `db/main.py`、`model/main.py` 之间产生循环 import。
- **`create_all`** 才是真正"动手"的一步：它会连上数据库，对花名册里每一张表检查"数据库里有没有这张表",没有就发一条真实的 `CREATE TABLE ...` SQL 建出来；已经存在的表会自动跳过，不会清空数据。
- **`run_sync(...)`** 存在的原因：`create_all` 本身是纯同步写的老函数，不认识 `await`。而 `conn` 是异步连接，两边"语言不通"。`run_sync` 就是专门做这个"翻译"工作的桥梁方法：把一个同步函数，安全地在异步环境里跑一遍，结果再 `await` 回来。

一句话总结这一行：**"用这个异步连接，把 metadata 花名册里登记过的表，真的在数据库里建出来。"**

---

## 2. `model/main.py` —— `Field` 和 `Column` 是两个不同世界的东西

```python
class Book(SQLModel, table=True):
    __tablename__ = "books"

    uid: uuid.UUID = Field(
        sa_column=Column(
            pg.UUID,
            nullable=False,
            primary_key=True,
            default=uuid.uuid4()
        )
    )

    title: str
    ...
```

`Book` 这个类同时扮演两个角色：**Pydantic 模型**（管 API 请求/响应的数据校验）和 **SQLAlchemy 表**（管数据库里这一列真实存成什么样）。这两个角色分别来自两个库：

| | 来自哪个库 | 管什么 |
|---|---|---|
| `Field` | Pydantic（SQLModel 包装过） | Python 这边的校验规则、默认值 |
| `Column` | SQLAlchemy | 数据库那一列的真实类型、约束 |

### 为什么 `title` 直接写 `str`，`uid` 却要 `Field(sa_column=Column(...))`

`Field` 自带一堆常用参数（`default`、`index`、`unique`、`foreign_key`、`max_length`...），能覆盖大部分需求，SQLModel 会根据类型注解自动帮你推断出合适的数据库列——`title: str` 这种没有特殊要求的字段，交给它自动处理就够了。

`uid` 这个字段有几个 `Field` 自带参数覆盖不到的特殊要求：

1. 想用 **PostgreSQL 专属**的 `UUID` 类型存储（`pg.UUID`），不是随便一个通用类型
2. 要手动指定 `primary_key=True`、`nullable=False`
3. 要指定"没给值时自动生成"的逻辑

`Field` 自己的参数列表里没有能覆盖"数据库专属类型"这种细粒度控制的选项，所以只能自己手搭一个 `Column(...)`，再通过 `sa_column=` 这个关键字参数交给 `Field`——**`Field` 是唯一的入口，SQLModel 只认 `Field(...)`，`Column` 必须包在它里面才能被正确处理，且 `sa_column` 是关键字参数，不能省略这个关键字直接位置传参**（`default` 才是 `Field` 的第一个位置参数，直接 `Field(Column(...))` 会把 `Column` 对象错误地当成 `default` 的值）。

一句话总结：**`Field` 参数够用就用 `Field` 自带的；不够用（比如要数据库专属类型/精细控制）才升级到 `Field(sa_column=Column(...))`，而且 `sa_column=` 这个关键字不能省。**

### `uuid.uuid4` 和 `uuid.uuid4()` 的区别（`default=uuid.uuid4()` 那个 bug 的根源）

这是 Python 里一个非常容易踩、但后果很隐蔽的坑——**加不加括号，意思完全不一样**：

| 写法 | 是什么 | 什么时候执行 |
|---|---|---|
| `uuid.uuid4` | **函数本身**（没有调用它） | 你没让它执行，只是把这个函数"指过去" |
| `uuid.uuid4()` | **调用这个函数、拿到调用后的结果** | **立刻执行**，马上生成一个具体的 UUID 值 |

放进 `default=` 参数里，这个区别会被放大成完全不同的行为：

- `default=uuid.uuid4`：意思是"把这个**函数**交给 SQLAlchemy，以后每次插入新行、需要默认值时，**你（SQLAlchemy）自己去调用它**，现场生成一个新的 UUID"。
- `default=uuid.uuid4()`：`uuid.uuid4()` 这半句在 `class Book` **这个类被 Python 加载的那一刻**（也就是程序刚启动、这个文件被 import 的时候）就已经执行完了，生成了一个**具体的、写死的 UUID 值**（比如 `a1b2c3d4-...`）。之后交给 `default` 的，只是这一个已经算好的固定值——**不是一个"每次都会重新生成"的函数**。结果就是：每一条没手动指定 `uid` 的新记录，拿到的都是**同一个值**，第二条数据插入时因为主键重复直接报错。

一个类比：`uuid.uuid4` 好比把"一台印章机"整个交给对方，对方需要的时候自己按一下、每次盖出来的都不一样；`uuid.uuid4()` 好比你自己先按了一下章、拿到一个具体的印记，然后把**这一个印记**（而不是印章机）交给对方——对方以后不管用多少次，拿到的都是同一个印记。

这个规律不只适用于 `uuid.uuid4`，`created_at`/`update_at` 用的 `default=datetime.now`（正确，没加括号）也是同样的道理：不加括号是把"生成当前时间的函数"交出去，每次插入时都会拿到**当下**的真实时间；如果写成 `datetime.now()`，则会变成"程序启动那一刻的固定时间"，之后插入的每一条记录，创建时间都会是同一个值，明显不对。

---

## 3. `config.py` —— `Settings` 类为什么这么写

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    model_config = SettingsConfigDict(
        env_file=".env",
        echo=True
    )

config = Settings()
```

- **继承 `BaseSettings`（而不是普通 `BaseModel`）**：`BaseSettings` 是 pydantic-settings 专门为"读配置"场景设计的基类，除了跟 `BaseModel` 一样做类型校验，还**自动**知道去读系统环境变量、`.env` 文件，不用自己写读文件的逻辑。
- **`DATABASE_URL: str`**：声明这个配置项必须存在、必须是字符串，缺失时会在 `Settings()` 实例化那一刻直接报 `ValidationError`（Field required），而不是等到真正用的时候才报错发现是 `None`——提前暴露问题。
- **`model_config = SettingsConfigDict(...)`**：pydantic v2 的标准配置方式。**必须叫 `model_config` 这个固定名字**，旧版本（v1）用的是嵌套 `class Config:` 写法，两种不能混用（比如写成 `Config = SettingsConfigDict(...)` 是无效的，两边规则都不认）。
  - `env_file=".env"`：告诉它去读项目里的 `.env` 文件
- **`config = Settings()`**：在模块加载时就直接实例化一次，后面全项目 `import config` 用的都是这**同一份**已经读取、校验过的配置对象。

### 为什么 `.env` 最好用绝对路径

相对路径是相对于"你执行命令时所在的目录"（当前工作目录，cwd）去找的，**不是相对于 `config.py` 这个文件本身的位置**。今天你可能是在项目根目录跑 `fastapi dev`，能找到 `.env`；明天你换个目录、或者换个人跑这个项目、或者用测试框架跑，只要 cwd 变了，`.env` 就找不到了，会重新报 `DATABASE_URL Field required` 这个错——这跟当初 `python config.py` 报错踩的坑是一模一样的原理。

推荐写法：用 `__file__` 算出 `config.py` 自己的绝对路径，再往上推到项目根目录，这样不管从哪个目录执行命令都能稳定找到：

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 按 config.py 实际层级调整

class Settings(BaseSettings):
    DATABASE_URL: str
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
    )
```

---

## 4. `life_span` —— 应用启动/关闭时要做的事

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def life_span(app: FastAPI):
    print("start")
    await init_db()
    yield
    print("end")

app = FastAPI(
    title="bookly",
    version="v1",
    lifespan=life_span
)
```

### 这是什么

`lifespan` 是 FastAPI 提供的钩子，用来定义**"应用启动时要跑一次的代码"**和**"应用关闭时要跑一次的代码"**——不是每个请求都跑，是整个服务的生命周期里各跑一次。

### `@asynccontextmanager` + `yield` 是怎么把一份代码拆成"启动"和"关闭"两半的

这是 Python 标准库 `contextlib` 提供的写法，`yield` 是分界线：

```python
print("start")      # ← yield 之前：应用启动时执行一次
await init_db()      #   （这里用来建表，确保服务真正开始处理请求前，数据库表已经就绪）
yield                # ← 分界线：服务正常运行、处理请求，全部发生在这里
print("end")         # ← yield 之后：应用关闭时执行一次（比如 Ctrl+C 停止服务）
```

服务启动时，FastAPI 会跑到 `yield` 就"暂停"在那里，把控制权交出去开始正常处理请求；等到服务准备关闭（进程收到退出信号），FastAPI 才会"回来"继续跑 `yield` 之后剩下的代码，做收尾工作（比如关闭数据库连接池、释放资源）。

### 为什么要用它，而不是直接在模块顶层调用 `init_db()`

如果直接在文件顶层写 `await init_db()`，会有两个问题：一是顶层代码不能直接 `await`（不在异步函数里）；二是没有"关闭时清理资源"这个配套机制。用 `lifespan` 能保证：**建表这件事，一定在 FastAPI 真正开始接收请求之前完成**，避免"服务已经能接请求了，但表还没建好"这种时序问题；同时也提供了一个统一的地方，未来要做"关闭时断开数据库连接"之类的收尾逻辑，都可以加在 `yield` 之后。

---

## 待办清单

- [ ] 修 `uid` 的 `default=uuid.uuid4()` → `uuid.uuid4`
- [ ] 修 `created_at`/`update_at` 补上 `sa_column=`
- [ ] 删掉 `config.py` 里无效的 `echo=True`
- [ ] `.env` 路径改成用 `Path(__file__)` 算绝对路径
