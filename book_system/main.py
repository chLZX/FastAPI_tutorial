books = [ 
{
        "id": 4,
        "title": "Fluent Python",
        "author": "Luciano Ramalho",
        "publisher": "O'Reilly Media",
        "published_date": "2022-04-26",
        "page_count": 1012,
        "language": "English",
    },
    {
        "id": 5,
        "title": "Effective Python",
        "author": "Brett Slatkin",
        "publisher": "Addison-Wesley",
        "published_date": "2019-11-23",
        "page_count": 480,
        "language": "English",
    },
    {
        "id": 6,
        "title": "Flask Web Development",
        "author": "Miguel Grinberg",
        "publisher": "O'Reilly Media",
        "published_date": "2018-03-01",
        "page_count": 322,
        "language": "English",
    },
    {
        "id": 7,
        "title": "Architecture Patterns with Python",
        "author": "Harry Percival",
        "publisher": "O'Reilly Media",
        "published_date": "2020-03-24",
        "page_count": 296,
        "language": "English",
    },
    {
        "id": 8,
        "title": "Two Scoops of Django",
        "author": "Daniel Roy Greenfeld",
        "publisher": "Two Scoops Press",
        "published_date": "2021-06-15",
        "page_count": 548,
        "language": "English",
    },
    {
        "id": 9,
        "title": "Python Crash Course",
        "author": "Eric Matthes",
        "publisher": "No Starch Press",
        "published_date": "2019-05-03",
        "page_count": 544,
        "language": "English",
    },
    {
        "id": 10,
        "title": "Designing Data-Intensive Applications",
        "author": "Martin Kleppmann",
        "publisher": "O'Reilly Media",
        "published_date": "2017-03-16",
        "page_count": 616,
        "language": "English",
    },
    {
        "id": 11,
        "title": "Building Microservices",
        "author": "Sam Newman",
        "publisher": "O'Reilly Media",
        "published_date": "2021-08-10",
        "page_count": 610,
        "language": "English",
    },
    {
        "id": 12,
        "title": "REST API Design Rulebook",
        "author": "Mark Masse",
        "publisher": "O'Reilly Media",
        "published_date": "2011-10-26",
        "page_count": 104,
        "language": "English",
    },
    {
        "id": 13,
        "title": "Python 数据分析实战",
        "author": "Wes McKinney",
        "publisher": "人民邮电出版社",
        "published_date": "2022-09-01",
        "page_count": 458,
        "language": "Chinese",
    }]

from fastapi import FastAPI, status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI()

class Book(BaseModel):
    id: int
    title: str
    author: str
    publisher: str
    published_date: str
    page_count: int
    language: str

class Book_Update(BaseModel):
    title: str
    author: str

@app.get("/book", response_model = List[Book])
async def get_all_book():
    return books

@app.get("/book/{book_id}", response_model = Book)#, status_code = status.HTTP_201_CREATED)
async def get_a_book(book_id: int) -> dict:
    for book in books:
        if book["id"] == book_id:
            return book
    raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "not found")

@app.post("/book/create_book", status_code=status.HTTP_201_CREATED)
async def create_book(book: Book) -> dict:
    new_book = book.model_dump()
    books.append(new_book)
    return new_book

@app.patch("/book/update/{book_id}")
async def update(book_id: int, update: Book_Update) -> dict:
    for book in books:
        if book["id"] == book_id:
            book["title"] = update.title
            book["author"] = update.author
            return {"message": "success"}
    raise HTTPException(status_code = status.HTTP_404_NOT_FOUND)

@app.delete("/book/delete/{book_id}")
async def delete(book_id: int) -> dict:
    for book in books:
        if book["id"] == book_id:
            books.remove(book)
            return {"message": "success"}
    raise HTTPException(status_code = status.HTTP_404_NOT_FOUND)


