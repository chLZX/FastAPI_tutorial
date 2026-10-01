import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from book_system.config import Config

passwd_context = CryptContext(
    schemes=["bcrypt"]
)

ACCESS_TOKEN_EXPIRY = 3600  # access token 有效期：秒
REFRESH_TOKEN_EXPIRY = 2  # refresh token 有效期：天


def generate_passwd_hash(password: str) -> str:
    return passwd_context.hash(password)


def verify_password(password: str, hash: str) -> bool:
    return passwd_context.verify(password, hash)


def create_access_token(
    user_data: dict,
    expiry: timedelta | None = None,
    refresh: bool = False,
) -> str:
    if expiry is None:
        expiry = timedelta(seconds=ACCESS_TOKEN_EXPIRY)

    payload = {
        "user": user_data,
        "exp": datetime.now(timezone.utc) + expiry,
        "jti": str(uuid.uuid4()),
        "refresh": refresh,
    }

    return jwt.encode(
        payload=payload,
        key=Config.JWT_SECRET,
        algorithm=Config.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            jwt=token,
            key=Config.JWT_SECRET,
            algorithms=[Config.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as e:
        logging.warning("Invalid token: %s", e)
        return None

