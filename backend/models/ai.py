"""
Pydantic Models for AI Vision Extraction Response Validation

These models validate the JSON response from GPT-4o Vision API,
ensuring it matches the BookLister schema exactly (no extra keys, no 'mapping' field).
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class CoreFields(BaseModel):
    """Core book metadata fields."""
    author: Optional[str] = None
    book_title: Optional[str] = None
    language: Optional[str] = None
    isbn10: Optional[str] = None
    isbn13: Optional[str] = None
    country_of_manufacture: Optional[str] = None
    edition: Optional[str] = None
    narrative_type: Optional[str] = None
    signed: Optional[bool] = None
    signed_by: Optional[str] = None
    vintage: Optional[bool] = None
    ex_libris: Optional[bool] = None
    inscribed: Optional[bool] = None
    intended_audience: List[str] = Field(default_factory=list)
    format: List[str] = Field(default_factory=list)
    genre: List[str] = Field(default_factory=list)
    publication_year: Optional[int] = None
    publisher: Optional[str] = None
    topic: List[str] = Field(default_factory=list)
    type: Optional[str] = None
    era: Optional[str] = None
    illustrator: Optional[str] = None
    literary_movement: Optional[str] = None
    book_series: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    physical_condition: Optional[str] = None


class AIDescription(BaseModel):
    """AI-generated description fields."""
    overview: str = Field(default="", description="Paragraph 1: The Hook - What makes this book special (2-3 sentences)")
    publication_details: str = Field(default="", description="Paragraph 2: Publisher, year, edition, features, ISBN (2-4 sentences)")
    physical_condition: str = Field(default="", description="Paragraph 3: Honest condition assessment (2-4 sentences)")


class Pricing(BaseModel):
    """Pricing hints and research terms."""
    research_terms: List[str] = Field(default_factory=list)
    starting_price_hint: Optional[float] = None
    floor_price_hint: Optional[float] = None
    pricing_notes: Optional[str] = Field(None, description="Brief rationale for price suggestion")


class Confidences(BaseModel):
    """Confidence scores for key fields (0-1)."""
    author: Optional[float] = Field(None, ge=0.0, le=1.0)
    book_title: Optional[float] = Field(None, ge=0.0, le=1.0)
    isbn13: Optional[float] = Field(None, ge=0.0, le=1.0)
    edition: Optional[float] = Field(None, ge=0.0, le=1.0)
    signed: Optional[float] = Field(None, ge=0.0, le=1.0)
    publication_year: Optional[float] = Field(None, ge=0.0, le=1.0)


class Validation(BaseModel):
    """Validation warnings, confidences, and source tracking."""
    warnings: List[str] = Field(default_factory=list)
    confidences: Confidences = Field(default_factory=Confidences)
    sources: Dict[str, List[int]] = Field(default_factory=dict)


class EnrichResult(BaseModel):
    """
    Complete enrichment result from GPT-4o Vision API.
    
    This model validates the strict JSON response from the vision extraction,
    ensuring no extra keys and no 'mapping' field.
    """
    ebay_title: str = Field(..., description="eBay listing title (will be clipped to 80 chars)")
    title_char_count: int = Field(..., ge=0, description="Character count of ebay_title")
    core: CoreFields = Field(default_factory=CoreFields)
    ai_description: AIDescription = Field(default_factory=AIDescription)
    pricing: Pricing = Field(default_factory=Pricing)
    validation: Validation = Field(default_factory=Validation)

    @field_validator('ebay_title')
    @classmethod
    def clip_title(cls, v: str) -> str:
        """Clip title to 80 characters."""
        if len(v) > 80:
            return v[:80].rstrip()
        return v

    @field_validator('title_char_count', mode='before')
    @classmethod
    def set_title_char_count(cls, v: Optional[int], info) -> int:
        """Set title_char_count from ebay_title length if not provided."""
        if v is not None:
            return v
        # Get ebay_title from data if available
        if hasattr(info, 'data') and isinstance(info.data, dict) and 'ebay_title' in info.data:
            return len(info.data['ebay_title'])
        return 0

    class Config:
        extra = 'forbid'  # Reject any extra keys (including 'mapping')
        validate_assignment = True

