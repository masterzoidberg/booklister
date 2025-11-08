from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from models import BookStatus, ConditionGrade


class BookBase(BaseModel):
    """Base book schema"""
    model_config = ConfigDict(from_attributes=True)
    
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[str] = None
    language: Optional[str] = None
    format: Optional[str] = None
    edition: Optional[str] = None
    isbn13: Optional[str] = None
    ocr_text: Optional[str] = None
    category_suggestion: Optional[str] = None
    condition_grade: ConditionGrade = ConditionGrade.GOOD
    defects: Optional[str] = None
    price_suggested: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    quantity: int = 1
    title_ai: Optional[str] = None
    description_ai: Optional[str] = None
    specifics_ai: Optional[Dict[str, Any]] = None
    ai_validation_errors: Optional[List[str]] = None
    book_type: Optional[str] = None  # "nonfiction", "fiction", "childrens", or None
    ocr_confidence: Optional[float] = None
    metadata_confidence: Optional[float] = None
    sources: Optional[List[str]] = None
    payment_policy_name: Optional[str] = None
    shipping_policy_name: Optional[str] = None
    return_policy_name: Optional[str] = None
    verified: bool = False
    exported: bool = False
    exported_at: Optional[int] = None
    export_notes: Optional[str] = None


class BookCreate(BookBase):
    """Schema for creating a book"""
    pass


class BookUpdate(BaseModel):
    """Schema for updating a book"""
    status: Optional[BookStatus] = None
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[str] = None
    language: Optional[str] = None
    format: Optional[str] = None
    edition: Optional[str] = None
    isbn13: Optional[str] = None
    ocr_text: Optional[str] = None
    category_suggestion: Optional[str] = None
    condition_grade: Optional[ConditionGrade] = None
    defects: Optional[str] = None
    price_suggested: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    quantity: Optional[int] = None
    title_ai: Optional[str] = None
    description_ai: Optional[str] = None
    specifics_ai: Optional[Dict[str, Any]] = None
    ai_validation_errors: Optional[List[str]] = None
    book_type: Optional[str] = None  # "nonfiction", "fiction", "childrens", or None
    ocr_confidence: Optional[float] = None
    metadata_confidence: Optional[float] = None
    payment_policy_name: Optional[str] = None
    shipping_policy_name: Optional[str] = None
    return_policy_name: Optional[str] = None
    verified: Optional[bool] = None
    exported: Optional[bool] = None
    exported_at: Optional[int] = None
    export_notes: Optional[str] = None


class ImageBase(BaseModel):
    """Base image schema"""
    model_config = ConfigDict(from_attributes=True)
    
    path: str
    width: int
    height: int
    hash: Optional[str] = None


class ImageCreate(ImageBase):
    """Schema for creating an image"""
    book_id: str


class Image(ImageBase):
    """Schema for image response"""
    id: str
    book_id: str


class Book(BookBase):
    """Schema for book response"""
    id: str
    status: BookStatus
    created_at: int
    updated_at: int
    images: List[Image] = []


class ExportBase(BaseModel):
    """Base export schema"""
    model_config = ConfigDict(from_attributes=True)
    
    file_path: str
    row_count: int


class Export(ExportBase):
    """Schema for export response"""
    id: str
    created_at: int


class SettingBase(BaseModel):
    """Base setting schema"""
    model_config = ConfigDict(from_attributes=True)
    
    value: Optional[Dict[str, Any]] = None


class Setting(SettingBase):
    """Schema for setting response"""
    key: str


class PolicyDefaults(BaseModel):
    """Schema for policy defaults"""
    payment_policy_name: Optional[str] = None
    shipping_policy_name: Optional[str] = None
    return_policy_name: Optional[str] = None


class ExportRequest(BaseModel):
    """Schema for export request"""
    book_ids: List[str]


class ScanResponse(BaseModel):
    """Schema for scan response"""
    isbn13: Optional[str] = None
    ocr_text: Optional[str] = None
    title_guess: Optional[str] = None
    author_guess: Optional[str] = None


class MetadataResponse(BaseModel):
    """Schema for metadata enrichment response"""
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[str] = None
    language: Optional[str] = None
    format: Optional[str] = None
    edition: Optional[str] = None
    category_suggestion: Optional[str] = None


class AIResponse(BaseModel):
    """Schema for AI generation response"""
    title_ai: str
    description_ai: str
    specifics_ai: Dict[str, Any]