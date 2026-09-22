from fastapi import FastAPI
from contextlib import asynccontextmanager
from book_system.db.main import init_db
from book_system.books.routes import book_router

@asynccontextmanager
async def life_span(app: FastAPI):
    print("start")
    await init_db()
    yield
    print("end")


app = FastAPI(
    title = "bookly",
    version = "v1",
    lifespan = life_span
)

app.include_router(book_router, prefix = f"/api/v1", tags = ["books"])