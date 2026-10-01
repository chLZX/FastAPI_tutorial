# Step 3：理解 `service.py` 与 `db/main.py` 中的 Session 操作

这一节我们把 `service.py` 里对数据库做增删改的三行代码，以及 `db/main.py` 里
`sessionmaker` / `Depends(get_session)` 这些"看起来眼熟但说不清楚"的东西，
一次性讲透。

---

## 一、`service.py` 里的三个操作

### 1. `session.add(new_book)` —— 新增

```python
new_book = Book(**book_data.model_dump())
session.add(new_book)
await session.commit()
```

**`new_book` 必须是一个 SQLModel 的类实例，并且这个 SQLModel 类必须声明了 `table=True`。**

为什么？

- SQLModel 有两种"模式"：
  - **纯 Pydantic 模式**（默认，`table=True` 不写）：只是一个普通的数据校验/序列化模型，
    比如你用来接收请求体的 `BookCreateModel`。它**不对应任何数据库表**，
    也没有 ORM 的"身份追踪"能力。
  - **ORM 模式**（`table=True`）：这个类同时也是一张真实的数据库表，
    每个实例对应表里的一行数据。只有这种类的实例，才能被 SQLAlchemy 的
    `Session` 识别、追踪状态（新增/修改/删除）、生成对应的 SQL。

```python
class Book(SQLModel, table=True):   # ← 这里的 table=True 是关键
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str
    author: str
    ...
```

`session.add(obj)` 本质上是把 `obj` 交给 SQLAlchemy 的"身份映射（Identity Map）"，
Session 会开始追踪这个对象的状态。如果 `obj` 只是一个普通的 Pydantic 对象
（没有 `table=True`），SQLAlchemy 根本不知道它对应哪张表、哪些列，会直接报错。

所以在实际写代码时，流程通常是：

```python
book_data_dict = book_data.model_dump()   # 前端传来的 Pydantic 请求模型 → dict
new_book = Book(**book_data_dict)          # 转换成"table=True"的 ORM 模型
session.add(new_book)                      # 现在才能被 session 追踪
await session.commit()                     # 落库
```

---

### 2. `setattr(book_to_update, key, value)` —— 修改

```python
book_to_update = await self.get_book(book_uid, session)

update_data_dict = update_data.model_dump()
for key, value in update_data_dict.items():
    setattr(book_to_update, key, value)

await session.commit()
```

**`setattr(obj, key, value)` 就是 Python 内置的"动态属性赋值"，等价于：**

```python
setattr(book_to_update, "title", "新标题")
# 完全等价于
book_to_update.title = "新标题"
```

只不过 `key` 是一个字符串变量（比如 `"title"`），没法直接写成
`book_to_update.key = value`（那样 Python 会真的去找一个叫 `key` 的属性，
而不是把 `key` 变量的值当作属性名）。所以要用 `setattr` 这种"用字符串
指定属性名"的写法，才能在 `for` 循环里批量、动态地更新任意字段。

**关键点在于：`book_to_update` 已经是从 `session` 查出来的、被这个 Session
追踪着的对象**（比如通过 `await session.get(Book, book_uid)` 或
`session.exec(select(Book)...)` 拿到的）。

也就是说：

1. 只要这个对象是**通过当前 session 查出来的**（它已经被 Session 的身份映射记录在案），
2. 那么你**只需要直接修改它的属性**（无论是 `obj.title = xxx` 还是 `setattr(obj, "title", xxx)`，
   效果一样），
3. SQLAlchemy 会自动检测到这个对象"脏了"（dirty，即属性被改过但还没同步到数据库），
4. 你**不需要**再手动调用 `session.add(book_to_update)`（因为它本来就已经在
   Session 的追踪范围内了），
5. 只需要最后 `await session.commit()`，SQLAlchemy 就会自动生成对应的
   `UPDATE ... SET title=..., author=... WHERE id=...` 并执行。

一句话总结：**"改对象属性 = 改数据库"，前提是这个对象是 Session 亲自查出来、
正在被追踪的对象；改完之后 `commit()` 一下就落库了。**

---

### 3. `session.delete(book_to_delete)` —— 删除

```python
book_to_delete = await self.get_book(book_uid, session)
await session.delete(book_to_delete)
await session.commit()
```

跟增、改一样，**删除也是直接把这个"被 Session 追踪的 ORM 对象"整个传给
`session.delete()`**，不需要你自己写 `DELETE FROM book WHERE id=...` 这种 SQL。

- `session.delete(obj)`：告诉 Session"把这个对象标记为待删除"。
- `await session.commit()`：真正执行删除的 SQL，并提交事务。

所以增删改三者的模式其实是统一的：

| 操作 | 你要做的事 | SQLAlchemy 帮你做的事 |
|---|---|---|
| 新增 | `session.add(obj)`（obj 是新建的 `table=True` 实例） | 追踪该对象 → commit 时生成 `INSERT` |
| 修改 | 直接改已被追踪对象的属性（`obj.x = y` 或 `setattr`） | 检测到属性变化 → commit 时生成 `UPDATE` |
| 删除 | `session.delete(obj)`（obj 是已被追踪的对象） | 标记删除 → commit 时生成 `DELETE` |

**核心思想：你操作的始终是 Python 对象本身，SQLAlchemy 负责把"对象状态的变化"
翻译成 SQL。这就是 ORM（对象关系映射）存在的意义。**

---

## 二、`db/main.py` 里的 Session 创建逻辑

```python
Session = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_session() -> AsyncSession:
    async with Session() as session:
        yield session
```

逐行拆解：

### 1. `sessionmaker(...)` —— 造一个"Session 工厂"

`sessionmaker` 本身**不是** Session，而是一个**用来生产 Session 的工厂函数**。
你配置好参数后，`Session` 这个变量就变成了一个"可调用对象"，
每次调用 `Session()` 都会**创建一个全新的 Session 实例**。

- `bind=async_engine`：告诉这个工厂"你造出来的每一个 Session，
  都要连接到 `async_engine` 这个数据库引擎上"。`async_engine` 是
  SQLAlchemy 用来真正管理数据库连接池、执行 SQL 的底层对象
  （通常是 `create_async_engine("postgresql+asyncpg://...")` 这样创建的）。

- `class_=AsyncSession`：默认情况下 `sessionmaker` 造出来的是**同步版**的
  `Session`。因为我们用的是异步数据库驱动（比如 `asyncpg`），
  所以要显式指定造出来的 Session 类型是 **`AsyncSession`**（异步版本），
  这样才能配合 `await session.commit()`、`await session.get(...)` 这种写法。

- `expire_on_commit=False`：这个参数决定了"**commit 之后，之前查出来的对象还能不能继续用**"。
  - SQLAlchemy 的默认行为（`expire_on_commit=True`）是：每次 `commit()` 之后，
    所有当前 Session 追踪的对象都会被标记为"过期（expired）"，
    下次你再访问这个对象的属性时（比如 `book.title`），
    SQLAlchemy 会**自动重新发一次 SELECT 去数据库刷新数据**，
    确保你拿到的永远是最新值。
  - 但在 Web 接口场景里，我们经常是：`commit()` 之后马上要把这个对象
    **返回给前端**（比如 FastAPI 用 response_model 序列化）。
    如果对象已经"过期"，而这时候 Session 可能已经关闭了
    （异步场景下再触发一次隐式查询很容易出问题，甚至报错：
    "greenlet_spawn has not been called" 之类的异步上下文错误）。
  - 所以设置 `expire_on_commit=False`：**commit 之后对象里的属性值保持不变
    （不会被标记过期，也不会自动重新查询），可以放心地直接拿去序列化返回。**
    这是异步 Web 框架里的常见、推荐做法。

### 2. `async with Session() as session: yield session` —— 依赖注入的核心

```python
async def get_session() -> AsyncSession:
    async with Session() as session:
        yield session
```

这个函数是一个**异步生成器（generator）**，专门设计给 FastAPI 的
`Depends()` 使用，作用可以拆成两部分：

- **`Session()`**：调用刚才那个工厂，**创建一个全新的、独立的 AsyncSession 实例**
  （每次调用 `get_session()` 都会拿到一个新的 session，互不影响，
  这样才能保证不同请求之间的数据库会话是隔离的，不会互相干扰）。

- **`async with ... as session`**：用异步上下文管理器包裹这个 session。
  好处是：**不管这次请求处理成功还是抛出异常**，
  `async with` 都会保证在代码块结束时**自动调用 `session.close()`**，
  把这个数据库连接归还给连接池。你不需要手动写
  `try/finally: await session.close()`，`async with` 帮你做了。

- **`yield session`**：这里不是 `return`，而是 `yield`。这一点非常关键：
  - 函数执行到 `yield session`，会把 `session` 这个对象"交出去"，
    然后**函数在这里暂停**，并不会立刻往下执行（也就是还没执行到
    `async with` 结束、还没 close）。
  - 这个"暂停点"会一直保持到**使用这个 session 的接口函数处理完请求为止**
    （比如你的 `create_book`、`update_book` 这些路由函数跑完了）。
  - 等路由函数返回结果之后，FastAPI 会自动"回来"继续执行
    `get_session()` 里 `yield` 之后剩下的代码——也就是
    `async with` 代码块正常退出，从而触发 `session.close()`。
  - 这种"yield 前是准备资源，yield 后是清理资源"的写法，
    就是 FastAPI 官方推荐的**"带清理逻辑的依赖（dependency with cleanup）"**模式。

一句话总结：`get_session()` 每次被调用，都会**造一个新的、专属于本次请求的
数据库会话，请求处理完自动关闭**，天然保证了"一个请求一个 Session、
用完就还给连接池"，避免连接泄漏，也避免多个请求共用一个 Session
导致的数据混乱。

---

## 三、为什么要用 `session: AsyncSession = Depends(get_session)`

在路由函数或者 service 层，你经常会看到这样的写法：

```python
@book_router.post("/")
async def create_book(
    book_data: BookCreateModel,
    session: AsyncSession = Depends(get_session),
):
    ...
```

### `Depends(get_session)` 是什么？

`Depends` 是 FastAPI 的**依赖注入（Dependency Injection）**机制。
`Depends(get_session)` 的意思是：

> "在真正执行 `create_book` 这个函数之前，请先帮我调用一次
> `get_session()`，把它返回（或者说 yield 出来）的结果，
> 自动填到 `session` 这个参数里。"

也就是说：

- 你**不需要**自己在每个接口里手动写：

```python
session = Session()
try:
    ...
finally:
    await session.close()
```

- 而是把"如何创建 session、如何在用完之后关闭 session"这件事，
  统一封装进 `get_session()` 这一个函数里，然后**用 `Depends()`
  告诉 FastAPI："每个需要用到数据库的接口，都请自动帮我调一下这个函数，
  拿到 session 给我用。"**

### 为什么要这样做（好处）？

1. **代码复用、不用重复写连接管理逻辑**：
   所有需要访问数据库的路由，只要写一个 `Depends(get_session)`，
   连接的创建、关闭全部自动处理，不需要每个接口都写一遍
   "创建连接 → try → finally 关闭"的模板代码。

2. **生命周期与"一次请求"绑定**：
   前面说过，`get_session()` 是个带 `yield` 的生成器。FastAPI 在
   处理一次 HTTP 请求时：
   - 请求进来 → 调用 `get_session()`，执行到 `yield` 拿到 session，注入给路由函数；
   - 路由函数（可能还调用了 service 层）用这个 session 做各种查询/增删改；
   - 路由函数返回响应之后，FastAPI 自动"回到" `get_session()` 里
     `yield` 之后的代码，触发 `session.close()`。

   这保证了**这个 session 的生命周期，正好等于这一次 HTTP 请求的生命周期**，
   不多不少，干净利落，不会出现"session 用完忘记关"或者
   "多个请求抢同一个 session"的问题。

3. **方便测试时替换（依赖覆盖）**：
   FastAPI 的 `Depends` 还有一个很实用的特性——测试时可以用
   `app.dependency_overrides[get_session] = get_test_session`
   把真实数据库的 session 替换成测试数据库（比如内存 SQLite）的 session，
   而完全不用改路由函数或 service 层的任何代码。这是手写
   "全局变量 session" 这种方式做不到的。

一句话总结：**`Depends(get_session)` 让 FastAPI 在每次请求时自动帮你
"发一个新的数据库会话、用完自动收回"，代码里你只管拿着这个 `session`
去查、增、删、改就行，完全不用操心连接怎么建立、怎么关闭。**

---

## 四、串起来看整个流程

以创建一本书为例，完整链路是这样的：

1. 请求进来 → FastAPI 发现路由函数依赖 `Depends(get_session)`；
2. FastAPI 调用 `get_session()` → 执行 `Session()` 造一个新的 `AsyncSession`
   → 执行到 `yield session`，把这个 session 交给路由函数；
3. 路由函数把 `session` 传给 `service.create_book(book_data, session)`；
4. `service.py` 里：
   ```python
   new_book = Book(**book_data.model_dump())  # 组装成 table=True 的 ORM 对象
   session.add(new_book)                       # 交给 session 追踪
   await session.commit()                      # 生成并执行 INSERT
   ```
5. 因为 `expire_on_commit=False`，`new_book` 对象上的数据在 commit 后
   依然可以直接读取，不会触发多余的隐式查询；
6. `new_book` 被返回给路由函数，FastAPI 用它序列化成 JSON 响应给前端；
7. 响应发出后，FastAPI 回到 `get_session()` 里 `async with` 代码块结束，
   自动 `session.close()`，把连接还给连接池。

这一整套设计，本质上都是在解决同一个问题：
**"怎么在异步、多请求并发的场景下，安全、干净、可复用地管理数据库会话。"**