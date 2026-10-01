from datetime import timedelta

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from book_system.db.main import get_session

from .dependencies import RefreshTokenBearer, get_current_user
from .models import User
from .schemas import UserCreateModel, UserLoginModel, UserModel
from .service import UserService
from .utils import REFRESH_TOKEN_EXPIRY, create_access_token, verify_password

auth_router = APIRouter()
user_service = UserService()


@auth_router.post(
    "/signup",
    response_model=UserModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_account(
    user_data: UserCreateModel,
    session: AsyncSession = Depends(get_session),
):
    email = user_data.email

    user_exists = await user_service.user_exists(email, session)

    if user_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with email already exists",
        )

    new_user = await user_service.create_user(user_data, session)

    return new_user


@auth_router.post("/login")
async def login_users(
    login_data: UserLoginModel,
    session: AsyncSession = Depends(get_session),
):
    email = login_data.email
    password = login_data.password

    user = await user_service.get_user_by_email(email, session)

    if user is not None:
        password_valid = verify_password(password, user.password_hash)

        if password_valid:
            access_token = create_access_token(
                user_data={
                    "email": user.email,
                    "user_uid": str(user.uid),
                }
            )

            refresh_token = create_access_token(
                user_data={
                    "email": user.email,
                    "user_uid": str(user.uid),
                },
                refresh=True,
                expiry=timedelta(days=REFRESH_TOKEN_EXPIRY),
            )

            return JSONResponse(
                content={
                    "message": "Login successful",
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "user": {
                        "email": user.email,
                        "uid": str(user.uid),
                    },
                }
            )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid Email Or Password",
    )


@auth_router.get("/refresh_token")
async def get_new_access_token(
    token_details: dict = Depends(RefreshTokenBearer()),
):
    new_access_token = create_access_token(
        user_data=token_details["user"],
    )

    return JSONResponse(content={"access_token": new_access_token})


@auth_router.get("/me", response_model=UserModel)
async def get_current_user_profile(
    user: User = Depends(get_current_user),
):
    return user
