# Book System：认证模块说明（JWT / Access Token / Refresh Token）

本文档解释 `auth/` 模块里 JWT 认证是怎么工作的，以及代码为什么这样写。
相关文件：

| 文件 | 作用 |
|---|---|
| `auth/utils.py` | 密码哈希、生成令牌、解码令牌 |
| `auth/routes.py` | `/signup`、`/login`、`/refresh_token`、`/me` 接口 |
| `auth/dependencies.py` | `AccessTokenBearer` / `RefreshTokenBearer`，校验请求里的令牌 |
| `config.py` | 从 `.env` 读取 `JWT_SECRET`、`JWT_ALGORITHM` |

---

## 1. 整体流程

```
注册:  明文密码 ──generate_passwd_hash (bcrypt)──▶ 只把哈希存进数据库
登录:  邮箱+密码 ──verify_password──▶ 通过 ──▶ 返回 access_token + refresh_token
访问:  请求头带 access_token ──▶ 服务器验证签名、是否过期 ──▶ 知道是谁
续期:  access_token 过期 ──▶ 用 refresh_token 调 /refresh_token ──▶ 换新的 access_token
```

HTTP 是无状态的，服务器不记得上一个请求是谁发的。登录成功后，服务器发给用户一个
JWT，用户之后每次请求都带上它来证明身份。服务器不需要存 session，只要验证签名即可。

---

## 2. 什么是 Access Token 和 Refresh Token

| | Access Token | Refresh Token |
|---|---|---|
| 用途 | 每次请求受保护接口（如 `/me`）时出示，证明“我是谁” | 只用来换新的 access token |
| 有效期 | 短（本项目 `ACCESS_TOKEN_EXPIRY = 3600` 秒，即 1 小时） | 长（本项目 `REFRESH_TOKEN_EXPIRY = 2` 天） |
| 使用频率 | 几乎每个请求都带 | 只在 access token 过期时用一次 |
| 在代码里怎么区分 | payload 中 `"refresh": False` | payload 中 `"refresh": True` |
| 谁来校验 | `AccessTokenBearer` | `RefreshTokenBearer` |

### 为什么要两个令牌？

JWT 一旦签发，服务器无法主动让它失效，只能等它自己过期。于是有一个两难：

- 有效期很长：令牌被偷了，攻击者能用很久。
- 有效期很短：用户要频繁重新输入密码，体验很差。

解决办法是分工：

- **access token 短命**：天天在网络上传输，被截获的风险高，但就算被偷，很快失效。
- **refresh token 长命**：只发往 `/refresh_token` 这一个接口，很少暴露，用来换新的 access token。

用户只要在 2 天内使用过，就一直保持登录状态，不用重新输入密码。

类比：access token 像当天的门禁卡，丢了影响有限；refresh token 像去前台换门禁卡用的凭证，平时收好。

### 为什么要区分类型（`refresh` 字段）

如果不区分，攻击者拿到长寿命的 refresh token，就能直接当 access token 访问所有接口，
“短命 access token”的设计就白做了。所以：

- 普通接口用 `AccessTokenBearer`：如果令牌里 `refresh` 为真，直接拒绝。
- `/refresh_token` 接口用 `RefreshTokenBearer`：如果令牌里 `refresh` 不为真，直接拒绝。

---

## 3. JWT 的结构

一个 JWT 是用两个点分成三段的字符串：

```
eyJhbGciOiJIUzI1NiIs...  .  eyJ1c2VyIjp7ImVtYWlsIjoi...  .  SflKxwRJSMeKKF2QT4...
        Header                         Payload                       Signature
```

签名的计算方式：

```
Signature = HMACSHA256( base64url(header) + "." + base64url(payload), 密钥 )
```

### Header 放什么

Header 说明“这个令牌怎么签名的”，通常就两项：

```json
{"alg": "HS256", "typ": "JWT"}
```

- `alg`：签名算法（本项目是 HS256）
- `typ`：令牌类型，固定写 `JWT`

**你不需要手动写 header。** `jwt.encode` 会根据 `algorithm` 参数自动生成它。
只有在需要额外信息（例如密钥编号 `kid`）时，才通过 `headers=` 参数自定义。

### Payload 放什么

Payload 放的是关于这个令牌和用户的“声明”（claims）。本项目登录时生成的 payload 是：

```json
{
  "user": {"email": "a@example.com", "user_uid": "5b1c...-uuid"},
  "exp": 1790000000,
  "jti": "c9a1f3e2-7b4d-4c8a-9e1f-2a3b4c5d6e7f",
  "refresh": false
}
```

| 字段 | 含义 |
|---|---|
| `user` | 用户信息（本项目放 `email` 和 `user_uid`），后面通过 email 去数据库查用户 |
| `exp` | 过期时间。`jwt.decode` 会自动检查，过期就抛异常 |
| `jti` | 令牌唯一 ID，将来做“退出登录 / 令牌黑名单”时用来标识某一个令牌 |
| `refresh` | 是否是 refresh token（见上一节） |

另外 JWT 标准里还有一些常用字段：`sub`（主体，通常是用户 ID）、`iat`（签发时间）、
`iss`（签发者）、`aud`（接收方）。本项目暂时没用到，但很多项目会用 `sub` 代替这里的 `user`。

**重要：payload 只是 Base64 编码，不是加密，任何人都能解码看到内容。**
所以绝对不要放密码、密码哈希、身份证号、银行卡号等敏感信息，也不要放太多数据（每个请求都要带着它）。

> 注：签名对象是“Base64URL 编码之后的字符串”，不是原始 JSON。`jwt.encode`
> 会自动完成编码，所以代码里看不到 base64 的步骤。Base64URL 是把标准 Base64 的 `+` `/`
> 换成 `-` `_` 并去掉末尾 `=`，这样令牌可以安全地放进 HTTP 头和 URL。

### 密钥（`JWT_SECRET`）是什么

密钥是**只有服务器知道的一段秘密字符串**，用来给令牌“盖章”，就像印章：

- 签发时：服务器用密钥对 `header.payload` 计算出签名，附在令牌末尾。
- 验证时：服务器取出令牌前两段，用同一个密钥重新算一遍，和令牌自带的签名比较。
  一致 → 内容没被改过、确实是我签发的；不一致 → 被篡改或伪造，拒绝。

攻击者能读到 payload，也可以改 payload，但没有密钥就算不出对应的新签名，
所以服务器一验证就能发现。**整个方案的安全性完全依赖于密钥不泄露。**

本项目里密钥通过 `.env` 文件配置，由 `config.py` 读取为 `Config.JWT_SECRET`：

```
JWT_SECRET=一段足够长且随机的字符串
JWT_ALGORITHM=HS256
```

使用密钥的注意事项：

- 要足够长、足够随机，不要用 `123456`、`secret` 这类字符串。生成方式：
  `python -c "import secrets; print(secrets.token_hex(32))"`
- **不要把 `.env` 提交到 Git**（确保它在 `.gitignore` 里）。
- 一旦泄露要立刻更换。更换后所有已发出的令牌都会失效，用户需要重新登录。
- HS256 是对称算法：签名和验证用同一个密钥。

---

## 4. 代码讲解

### 4.1 `timedelta` 是什么

`timedelta` 来自 Python 标准库 `datetime`，表示**一段时间长度**（不是某个时间点）。

```python
from datetime import timedelta

timedelta(seconds=3600)   # 1 小时
timedelta(days=2)         # 2 天
timedelta(hours=1, minutes=30)  # 1 小时 30 分
```

它可以和时间点相加，得到“多久之后”的时间点：

```python
datetime.now(timezone.utc) + timedelta(days=2)   # 两天后的此刻
```

本项目里用它计算令牌的过期时间：

```python
"exp": datetime.now(timezone.utc) + expiry
```

即“当前时间 + 有效时长 = 过期时间”。`expiry` 为空时默认用 `ACCESS_TOKEN_EXPIRY`（1 小时）；
创建 refresh token 时，路由里传入 `timedelta(days=REFRESH_TOKEN_EXPIRY)`（2 天）。

> 这里用 `timezone.utc`（带时区的 UTC 时间）而不是无时区的 `datetime.now()`，
> 是因为 JWT 的 `exp` 是按 UTC 时间戳计算的，用 UTC 可以避免服务器所在时区带来的偏差。

### 4.2 生成令牌：`jwt.encode`

```python
return jwt.encode(
    payload=payload,
    key=Config.JWT_SECRET,
    algorithm=Config.JWT_ALGORITHM,
)
```

三个参数分别是：

| 参数 | 作用 |
|---|---|
| `payload` | 要放进令牌的内容，变成令牌的第二段 |
| `key` | 密钥，参与计算第三段签名 |
| `algorithm` | 决定 header 里写什么，以及用哪种算法签名 |

为什么这样写：

1. **header 和签名不用自己提供**。它们都可以由这三样东西推导出来，`jwt.encode`
   内部自动完成“生成 header → Base64URL 编码 → HMAC-SHA256 签名 → 拼成
   `header.payload.signature`”的全过程。
2. **密钥和算法都从 `Config` 读取**，不写死在代码里，方便不同环境（开发 / 生产）使用不同密钥，
   也避免密钥被提交到代码仓库。
3. **显式传 `algorithm`**。PyJWT 的 `encode` 默认就是 HS256，不传也能运行，
   但显式传入有两个好处：代码一眼能看出用什么算法；`encode` 和 `decode` 都读同一个
   `Config.JWT_ALGORITHM`，以后改算法只改一处，不会出现两边不一致。

### 4.3 验证令牌：`jwt.decode`

```python
return jwt.decode(
    jwt=token,
    key=Config.JWT_SECRET,
    algorithms=[Config.JWT_ALGORITHM],
)
```

`decode` 做的事：用密钥重新计算签名并比对，检查 `exp` 是否过期，通过后返回 payload 字典；
签名不对、已过期、格式错误都会抛出异常。项目里用 `except jwt.PyJWTError` 统一捕获，
返回 `None`，由 `TokenBearer` 转成 401 响应。

### 4.4 一定要写 `algorithms` 吗？

**一定要。** PyJWT 的 `decode` 没有默认值，不写会直接报错：

```
It is required that you pass in a value for the "algorithms" argument when calling decode().
```

这是故意设计的，目的是防止“算法混淆攻击”。令牌的 header 里自带 `alg` 字段，
如果验证时“令牌说用什么算法就用什么”，攻击者就可以自己改 header：

- 改成 `"alg": "none"`，声称这个令牌不需要签名，直接绕过验证。
- 在使用 RSA 的系统中，把 `RS256` 改成 `HS256`，再拿**公开的公钥**当 HMAC 密钥签名，
  骗过按令牌声明算法验证的服务器。

所以验证用什么算法，必须由服务器明确规定，而不是由令牌自己说了算。
`algorithms` 就是一份**白名单**：令牌的 `alg` 不在名单里就直接拒绝。

写法上的两个细节：

- 参数名是 `algorithms`（复数），值是**列表**：`[Config.JWT_ALGORITHM]`，不要写成字符串。
- 列表里只放实际使用的算法，不要为了省事把所有算法都写进去，否则白名单就失去意义。

对比 `encode`：签发时由服务器自己决定算法，所以 `algorithm` 可以有默认值；
验证时输入来自不可信的外部，所以 `algorithms` 必须显式指定。

---

## 5. 接口一览

| 接口 | 需要的令牌 | 说明 |
|---|---|---|
| `POST /signup` | 无 | 注册，密码用 bcrypt 哈希后存库 |
| `POST /login` | 无 | 验证密码，返回 `access_token` 和 `refresh_token` |
| `GET /refresh_token` | **refresh token** | 用 refresh token 换新的 access token |
| `GET /me` | **access token** | 返回当前登录用户信息 |

请求受保护接口时，在请求头里带上：

```
Authorization: Bearer <token>
```

---

## 6. 已知的改进方向

当前实现能正常工作，若要用于生产环境，可以考虑：

1. **函数改名**：`create_access_token` 实际也用来生成 refresh token，建议改名为 `create_token`，或拆成两个函数。
2. **默认过期时间跟随令牌类型**：目前 `expiry` 为空时总是用 access token 的时长，
   如果创建 refresh token 时忘了传 `expiry`，它会变成短命令牌。可以改为 `refresh=True` 时默认用 refresh 的时长。
3. **缩小 payload**：`user` 里只放必要字段，避免敏感信息；也可以用标准字段 `sub` 存用户 ID，并加上 `iat`。
4. **支持撤销令牌**：已经有 `jti`，可以把退出登录的令牌 `jti` 存入黑名单（如 Redis），验证时检查。
5. **刷新令牌轮换**：每次换新 access token 时同时签发新的 refresh token，并让旧的作废，
   这样 refresh token 被偷后更容易被发现。
6. **生产环境务必使用 HTTPS**，令牌被截获就能被冒用。
