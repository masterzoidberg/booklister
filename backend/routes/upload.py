"""
Upload routes for BookLister AI
"""
import os
import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlmodel import Session

from models import Book, Image, BookStatus, ConditionGrade
from db import get_session, engine
from services.filesystem import fs_service
from services.vision_extraction import VisionExtractionService
from schemas import Book as BookSchema
from datetime import datetime

router = APIRouter(prefix="/ingest", tags=["upload"])

def extract_folder_info(files: List[UploadFile], folder_info_str: str = None) -> Dict[str, List[UploadFile]]:
    """Extract folder information and group files"""
    files_by_folder = {}
    
    if folder_info_str:
        try:
            import json
            folder_info = json.loads(folder_info_str)
        except json.JSONDecodeError:
            folder_info = {}
    else:
        folder_info = {}
    
    for file in files:
        # Try to get folder from provided info first
        if file.filename in folder_info:
            folder_name = folder_info[file.filename]
        else:
            # Extract folder from filename path if available
            if '/' in file.filename:
                folder_name = file.filename.split('/')[0]
            elif '\\' in file.filename:
                folder_name = file.filename.split('\\')[0]
            else:
                folder_name = "General"
        
        if folder_name not in files_by_folder:
            files_by_folder[folder_name] = []
        files_by_folder[folder_name].append(file)
    
    return files_by_folder

@router.post("/upload", response_model=List[BookSchema])
async def upload_images(
    session: Session = Depends(get_session),
    files: List[UploadFile] = File(...),
    folder_info: str = Form(None)
):
    """
    Upload images and create book records
    Supports folder-based organization with cross-browser compatibility
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    
    if len(files) > 100:  # Reasonable limit
        raise HTTPException(
            status_code=400, 
            detail="Too many files uploaded (max 100 per request)"
        )
    
    created_books = []
    
    try:
        # Group files by folder
        files_by_folder = extract_folder_info(files, folder_info)
        
        # Create a book for each folder
        for folder_name, folder_files in files_by_folder.items():
            # Create book record
            book = Book(status="new")
            session.add(book)
            session.commit()
            session.refresh(book)
            
            # Save images for this book
            for file in folder_files:
                try:
                    filename, width, height = fs_service.save_file(file, book.id)
                    
                    # Create image record
                    image = Image(
                        book_id=book.id,
                        path=filename,  # Store only relative path
                        width=width,
                        height=height
                    )
                    session.add(image)
                    
                except HTTPException:
                    # Re-raise HTTP exceptions
                    raise
                except Exception as e:
                    # Clean up book on image save failure
                    session.rollback()
                    try:
                        session.delete(book)
                        session.commit()
                        fs_service.delete_book_directory(book.id)
                    except:
                        pass
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to save image {file.filename}: {str(e)}"
                    )
            
            session.commit()
            session.refresh(book)

            # AI extraction disabled during upload - user must select category first
            # Workflow: Upload → Review page → Select category → Click "Extract with AI"
            # This ensures AI only extracts fields valid for the chosen eBay category
            book.status = BookStatus.NEW
            session.add(book)
            session.commit()
            session.refresh(book)

            created_books.append(book)
        
        return created_books
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Clean up any created books on general failure
        session.rollback()
        for book in created_books:
            try:
                with Session(engine) as cleanup_session:
                    cleanup_session.delete(book)
                    cleanup_session.commit()
                    fs_service.delete_book_directory(book.id)
            except:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )

@router.get("/upload-status")
async def get_upload_status():
    """Get upload service status and limits"""
    return {
        "status": "ready",
        "max_file_size": "10MB",
        "max_files_per_request": 100,
        "allowed_extensions": list(fs_service.ALLOWED_EXTENSIONS),
        "allowed_mime_types": list(fs_service.ALLOWED_MIME_TYPES)
    }
