from fastapi import APIRouter, status
from fastapi.exceptions import HTTPException
from book_system.books.book_data import books
from book_system.books.schemas import Book, Book_Update
from typing import List
book_router = APIRouter()


@book_router.get("/book", response_model = List[Book])
async def get_all_book():
    return books

@book_router.get("/book/{book_id}", response_model = Book)#, status_code = status.HTTP_201_CREATED)
async def get_a_book(book_id: int) -> dict:
    for book in books:
        if book["id"] == book_id:
            return book
    raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "not found")

@book_router.post("/book/create_book", status_code=status.HTTP_201_CREATED)
async def create_book(book: Book) -> dict:
    new_book = book.model_dump()
    books.append(new_book)
    return new_book

@book_router.patch("/book/update/{book_id}")
async def update(book_id: int, update: Book_Update) -> dict:
    for book in books:
        if book["id"] == book_id:
            book["title"] = update.title
            book["author"] = update.author
            return {"message": "success"}
    raise HTTPException(status_code = status.HTTP_404_NOT_FOUND)

@book_router.delete("/book/delete/{book_id}")
async def delete(book_id: int) -> dict:
    for book in books:
        if book["id"] == book_id:
            books.remove(book)
            return {"message": "success"}
    raise HTTPException(status_code = status.HTTP_404_NOT_FOUND)


