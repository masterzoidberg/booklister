from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
import logging
from typing import List, Optional
from contextlib import asynccontextmanager

from db import get_session, create_db_and_tables, init_default_settings, engine
from db import migrate
from models import Book, BookStatus
from schemas import Book as BookSchema, BookUpdate
from routes.upload import router as upload_router
from routes import ai_vision
from routes import ai_settings
from routes import ebay_oauth
from routes import ebay_publish
from routes import ebay_policies
from routes import ebay_categories

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    create_db_and_tables()
    migrate.ensure_schema(engine)  # Ensure AI columns exist
    init_default_settings()
    yield
    # On shutdown
    # (add any cleanup code here if needed)

# Initialize FastAPI app
app = FastAPI(
    title="BookLister AI API",
    description="Local book listing automation API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware - restrict to localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler for consistent error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "detail": exc.detail,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "detail": "Internal server error",
            "status_code": 500
        }
    )

# Mount static files for images
app.mount("/images", StaticFiles(directory="data/images"), name="images")

# Include routes
app.include_router(upload_router)
app.include_router(ai_vision.router)
app.include_router(ai_settings.router)
app.include_router(ebay_oauth.router)
app.include_router(ebay_publish.router)
app.include_router(ebay_policies.router)
app.include_router(ebay_categories.router)

# Routes
@app.get("/")
async def root():
    return {"message": "BookLister AI API is running"}


@app.get("/queue", response_model=List[BookSchema])
async def get_queue(
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """Get books in the queue, optionally filtered by status"""
    query = select(Book)
    if status:
        query = query.where(Book.status == BookStatus(status))
    
    books = session.exec(query).all()
    return books


@app.get("/book/{book_id}", response_model=BookSchema)
async def get_book(book_id: str, session: Session = Depends(get_session)):
    """Get a specific book by ID"""
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.put("/book/{book_id}", response_model=BookSchema)
async def update_book(
    book_id: str, 
    book_update: BookUpdate, 
    session: Session = Depends(get_session)
):
    """Update a book"""
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Update fields
    update_data = book_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(book, field, value)
    
    # Update timestamp
    from datetime import datetime
    book.updated_at = int(datetime.now().timestamp() * 1000)
    
    session.add(book)
    session.commit()
    session.refresh(book)
    return book


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)