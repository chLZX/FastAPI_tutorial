# Book System — FastAPI 学习项目

一个用来练习 FastAPI 核心概念的图书管理 API,提供图书的增删改查(CRUD)接口。

## 快速开始

```bash
# 安装依赖(第一次)
uv sync

# 开发模式启动(自动重载,只监听本机)
uv run fastapi dev book_system/main.py

# 生产模式启动(不自动重载,监听所有网卡)
uv run fastapi run book_system/main.py
```

启动后打开浏览器访问 `http://127.0.0.1:8000/docs`,可以在交互式文档里直接测试所有接口。

---

## 核心概念解析

以下概念全部结合本项目 `book_system/main.py` 里实际用到的代码来讲解。

### 1. 路径参数(Path Parameters)

写在 URL 路径本身里的一部分,用 `{}` 包起来,FastAPI 会自动把这部分值传给函数里同名的参数。本项目里 `book_id` 就是路径参数,用在查询单本书、更新、删除这三个接口上:

```python
@app.get("/book/{book_id}", response_model=Book)
async def get_a_book(book_id: int) -> dict:
    for book in books:
        if book["id"] == book_id:
            return book
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
```

访问方式是直接拼在 URL 里,比如查 id 为 5 的书:

```
GET /book/5
```

路径参数的特点是**位置固定、语义上代表"定位到哪一个资源"**,并且默认是必填的——URL 里必须有这一段,不能省略。

### 2. 查询参数(Query Parameters)

写在 URL 问号 `?` 后面、以 `key=value` 形式出现的参数,通常用来做筛选、排序、分页这类"附加条件"。本项目目前还没有用到查询参数,但如果想给 `/book` 接口加一个"按语言筛选"的功能,可以这样写:

```python
@app.get("/book", response_model=List[Book])
async def get_all_book(language: str):
    return [b for b in books if b["language"] == language]
```

调用方式:

```
GET /book?language=English
```

判断一个参数是路径参数还是查询参数的规则很简单:只要这个参数**没有出现在路径的 `{}` 里**,并且**类型不是 Pydantic 模型**,FastAPI 就会把它当成查询参数处理。上面例子里的 `language` 因为不满足前两个条件之一,所以自动被识别为查询参数,而且因为没给默认值,它是**必填**的查询参数,不传会报 422 错误。

### 3. 可选查询参数(Optional Query Parameters)

给查询参数加上默认值,它就变成了"可以不传"的可选参数,不传的时候就用默认值。真正决定是否必填的是**有没有默认值**,和写不写 `Optional` 关系不大(`Optional` 只表示"这个值可以是 None",本身不代表可以不传)。继续用上面的例子:

```python
from typing import Optional

@app.get("/book", response_model=List[Book])
async def get_all_book(language: Optional[str] = None):
    if language:
        return [b for b in books if b["language"] == language]
    return books
```

这样一来:

```
GET /book                    # 不传 language,返回全部书
GET /book?language=Chinese   # 传了 language,只返回中文书
```

### 4. 请求体(Request Body)

用于传递结构化的 JSON 数据,通常用在 POST / PUT / PATCH 这种需要提交较多字段的场景。请求体的数据不出现在 URL 上,而是放在 HTTP 请求的 body 里,用 Pydantic 模型(继承自 `BaseModel`)来声明它的结构和校验规则。

本项目里创建图书用到了请求体:

```python
class Book(BaseModel):
    id: int
    title: str
    author: str
    publisher: str
    published_date: str
    page_count: int
    language: str

@app.post("/book/create_book", status_code=status.HTTP_201_CREATED)
async def create_book(book: Book) -> dict:
    new_book = book.model_dump()
    books.append(new_book)
    return new_book
```

调用时需要在请求体里带上完整 JSON:

```json
{
  "id": 14,
  "title": "示例书名",
  "author": "示例作者",
  "publisher": "示例出版社",
  "published_date": "2026-01-01",
  "page_count": 300,
  "language": "Chinese"
}
```

更新图书用的是另一个更小的模型 `Book_Update`,同样通过请求体传入:

```python
class Book_Update(BaseModel):
    title: str
    author: str
```

> 小提示:`Book_Update` 里的 `title`、`author` 都是必填字段(没给默认值)。如果想让 `/book/update/{book_id}` 真正支持"只改其中一个字段"的 PATCH 语义,可以把两个字段都改成 `Optional[str] = None`,再配合 `model_dump(exclude_unset=True)` 判断调用方到底传了哪些字段。

### 5. response_model

`response_model` 是路由装饰器(`@app.get`、`@app.post` 等)里的一个参数,用来声明"这个接口**返回**的数据应该长什么样"。它的作用不只是文档展示,还会真正对你 `return` 的数据做一次校验和序列化,并且**自动过滤掉模型里没有声明的多余字段**,避免不小心把内部数据泄露出去。

本项目里两处用到了它:

```python
@app.get("/book", response_model=List[Book])   # 返回的是"一批" Book
async def get_all_book():
    return books

@app.get("/book/{book_id}", response_model=Book)  # 返回的是"一个" Book
async def get_a_book(book_id: int) -> dict:
    ...
```

注意 `List[Book]` 和 `Book` 的区别:前者表示返回值是一个列表,列表里每一项都应该符合 `Book` 结构;后者表示返回值本身就是一个 `Book` 对象。如果实际返回的数据形状和 `response_model` 声明的不一致(比如该用 `List[Book]` 却写成了 `Book`),FastAPI 会在响应阶段校验失败,直接抛出 `500 Internal Server Error`,因为这属于服务端自己的 bug,而不是客户端传参的问题。

另外,函数签名后面 `-> dict` 这种箭头返回类型注解,只是 Python 语法层面给人和 IDE 看的类型提示,并不会影响 `response_model` 的实际校验行为——两者是分开的两件事。

### 6. model_dump()

`model_dump()` 是 Pydantic 模型实例的方法,作用是把它转换成一个普通的 Python `dict`。本项目在创建图书时用到:

```python
async def create_book(book: Book) -> dict:
    new_book = book.model_dump()   # 把 Book 实例转成 dict
    books.append(new_book)          # books 列表里存的都是 dict,所以要先转换
    return new_book
```

因为 `books` 这个"数据库"用的是普通字典列表,而 FastAPI 传进来的 `book` 参数是一个 `Book` 类型的对象(不是 dict),所以需要先用 `model_dump()` 转换一下格式,才能塞进 `books` 列表里,保持数据结构统一。

常用变体还有 `model_dump_json()`(直接转成 JSON 字符串)和 `model_dump(exclude_unset=True)`(只导出调用方实际传了值的字段,常用在 PATCH 部分更新场景)。

### 7. status_code

`status_code` 是路由装饰器上的参数,用来指定"这个接口**执行成功时**返回的 HTTP 状态码"。不设置的话,FastAPI 默认用 `200 OK`。本项目在创建图书成功时,显式指定了更符合语义的 `201 Created`:

```python
@app.post("/book/create_book", status_code=status.HTTP_201_CREATED)
async def create_book(book: Book) -> dict:
    ...
```

`status.HTTP_201_CREATED` 本质上就是数字 `201`,只是用常量写法更易读。这是 RESTful 规范里的约定:GET 查询成功用 `200`,POST 创建成功用 `201`,DELETE 删除成功有时用 `204`。

需要注意的是,这个状态码只在函数**正常执行完并返回**的情况下生效;如果请求数据没通过 Pydantic 校验,FastAPI 会在执行函数之前就直接返回 `422`,跟这里设置的 `status_code` 无关;如果函数内部自己抛出了 `HTTPException`,用的也是异常里指定的状态码,而不是装饰器上这个默认值。

### 8. HTTPException

`HTTPException` 是 FastAPI 提供的一个异常类,用来主动中断请求处理、并返回一个指定的错误状态码和错误信息给客户端。本项目里在"查不到 / 改不到 / 删不到指定 id 的书"时用到:

```python
@app.get("/book/{book_id}", response_model=Book)
async def get_a_book(book_id: int) -> dict:
    for book in books:
        if book["id"] == book_id:
            return book
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
```

当循环遍历完 `books` 都没找到匹配的 `id`,就会 `raise` 这个异常。FastAPI 捕获到 `HTTPException` 后,不会让程序崩溃,而是自动把它转换成一个标准的错误响应返回给客户端,比如:

```json
{
  "detail": "not found"
}
```

同时响应状态码会被设置成你传的 `status_code`(这里是 `404 Not Found`)。`detail` 参数是可选的,用来告诉调用方具体的错误原因,本项目 `update` 和 `delete` 两个接口里 `raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)` 就没传 `detail`,也是合法的写法,只是错误信息会用 FastAPI 的默认文案。

---

## `fastapi dev` 与 `fastapi run` 的区别

两者背后都是用 `uvicorn` 启动服务,区别在于面向的场景不同:

| | `fastapi dev` | `fastapi run` |
|---|---|---|
| 使用场景 | 本地开发调试 | 生产环境部署 |
| 自动重载(改代码自动重启) | 默认开启 | 默认关闭 |
| 默认监听地址 | `127.0.0.1`(只有本机能访问) | `0.0.0.0`(允许外部/局域网访问) |
| 终端输出 | 更详细、更友好(会提示文档地址等) | 更简洁 |

简单说:日常写代码、边改边测就用 `fastapi dev`;真正要把服务部署到服务器上给别人访问,或者需要让同一网络里的其他设备连接,就用 `fastapi run`。

---

## 接口一览

| 方法 | 路径 | 说明 | 参数来源 |
|---|---|---|---|
| GET | `/book` | 获取所有图书 | 无 |
| GET | `/book/{book_id}` | 获取指定 id 的图书 | 路径参数 |
| POST | `/book/create_book` | 创建一本新书 | 请求体(`Book`) |
| PATCH | `/book/update/{book_id}` | 更新指定 id 图书的标题和作者 | 路径参数 + 请求体(`Book_Update`) |
| DELETE | `/book/delete/{book_id}` | 删除指定 id 的图书 | 路径参数 |
