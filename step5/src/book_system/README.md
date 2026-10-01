# 密码哈希与 `Field(exclude=True)` 说明

## 一、密码哈希工具代码

```python
from passlib.context import CryptContext

passwd_context = CryptContext(
    schemes = ["bcrypt"]
)

def generate_passwd_hash(password: str)->str:
    hash = passwd_context.hash(password)
    return hash

def verify_password(password: str, hash: str)->bool:
    return passwd_context.verify(password, hash)
```

**整体作用：** 注册时把明文密码变成哈希再存入数据库；登录时校验用户输入的密码是否正确。数据库里**永远不要存明文密码**。

### 1. `CryptContext(schemes=["bcrypt"])`

创建 passlib 的密码上下文，指定使用 **bcrypt** 算法。

- `schemes` 是列表，可以放多个算法。
- 第一个是默认算法，用来生成新哈希；其余的只用于验证旧哈希，方便以后迁移算法。

### 2. `generate_passwd_hash(password)`：生成哈希

```python
def generate_passwd_hash(password: str) -> str:
    hash = passwd_context.hash(password)
    return hash
```

- 参数 `password`：用户输入的明文密码。
- 返回值：bcrypt 哈希字符串，例如 `$2b$12$KIXQ...`（约 60 个字符）。
- bcrypt 每次会**随机生成 salt（盐）**，并把算法标识、成本因子、salt 和哈希值拼在同一个字符串里。
- 所以**同一个密码每次哈希结果都不一样**，这是正常现象。

哈希字符串结构：

```
$2b$   12   $   前22字符是salt   后31字符是哈希值
 │      │
 │      └ 成本因子（2^12 次迭代，越大越慢越安全）
 └ bcrypt 版本标识
```

### 3. `verify_password(password, hash)`：校验密码

```python
def verify_password(password: str, hash: str) -> bool:
    return passwd_context.verify(password, hash)
```

- `password`：用户登录时输入的明文密码。
- `hash`：数据库里存的哈希。
- 返回 `True` 表示匹配，`False` 表示不匹配。

`verify` 内部会：

1. 从存储的哈希里取出算法、成本因子和 salt；
2. 用同样的 salt 对输入的密码重新计算；
3. 用恒定时间比较两个结果（防止时序攻击）。

**为什么不能自己再 hash 一次然后用 `==` 比较？** 因为每次 salt 都不同：

```python
generate_passwd_hash("abc123") == generate_passwd_hash("abc123")  # False
```

必须用 `verify`，它会复用存储哈希里的 salt。

### 使用示例

```python
h = generate_passwd_hash("abc123")

verify_password("abc123", h)   # True
verify_password("abc124", h)   # False
```

### 登录流程示意

```python
user = get_user_from_db(email)
if user and verify_password(input_password, user.password_hash):
    ...  # 登录成功
else:
    ...  # 邮箱或密码错误
```

### 小建议

`hash` 是 Python 内置函数名，用作变量名/参数名会遮蔽内置函数。更好的写法：

```python
def generate_passwd_hash(password: str) -> str:
    return passwd_context.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    return passwd_context.verify(password, hashed_password)
```

### 注意事项

- **passlib 基本不再维护**，和新版 `bcrypt`（4.1+，尤其 5.x）搭配时可能出现警告甚至报错。可固定版本（如 `bcrypt==4.0.1`），或改用 `bcrypt` 库 / `argon2-cffi`。
- bcrypt 只处理密码的前 **72 字节**，超长部分会被忽略（新版 bcrypt 库甚至会直接报错）。

---

## 二、`password_hash: str = Field(exclude=True)`

```python
password_hash: str = Field(exclude=True)
```

这是 **Pydantic v2** 的写法，意思是：**这个字段在把模型导出（序列化）成字典或 JSON 时会被排除，不会出现在输出里。**

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    username: str
    password_hash: str = Field(exclude=True)

u = User(username="alice", password_hash="abc123")

u.password_hash          # "abc123"，属性照常可以访问
u.model_dump()           # {'username': 'alice'}，没有 password_hash
u.model_dump_json()      # '{"username":"alice"}'
```

**要点：**

- `exclude=True` 只影响**序列化输出**（`model_dump()`、`model_dump_json()`，以及 FastAPI 返回响应时的序列化）。
- 输入验证不受影响：创建对象时仍然要传 `password_hash`（除非给了默认值）。
- 对象里的值还在，代码里 `u.password_hash` 照样能读到。

**典型用途：** 防止敏感字段（密码哈希、内部 token 等）不小心通过 API 响应泄露给客户端。

**补充：** 字段级的 `exclude=True` 不能靠调用参数临时覆盖回来，更稳妥的做法是为 API 响应单独定义一个不含该字段的模型（如 `UserOut`）。

---

## 三、两者的关系

1. 用户注册 → `generate_passwd_hash(明文密码)` → 得到哈希；
2. 哈希存进数据库的 `password_hash` 字段；
3. 返回用户信息的 API 因为 `Field(exclude=True)`，不会把 `password_hash` 输出给客户端；
4. 用户登录 → `verify_password(输入密码, user.password_hash)` 校验。
