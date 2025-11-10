"""
Vision Extraction Service - Uses AI vision models to extract structured book metadata from images.

This service replaces OCR + metadata enrichment by directly calling AI Vision APIs
to extract all book fields in a single call, producing strict JSON matching BookLister schema.

Supports OpenAI (GPT-4o/GPT-5), OpenRouter, and Google Gemini providers.
"""

import os
import base64
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from pydantic_settings import BaseSettings
from openai import OpenAI
from sqlmodel import Session

from ai.prompt_booklister import SYSTEM_PROMPT, build_user_prompt
from models.ai import EnrichResult

logger = logging.getLogger(__name__)

# Try to import Google Gemini SDK
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed - Gemini provider unavailable")


class VisionExtractionService(BaseSettings):
    """Service for GPT-4o multimodal book metadata extraction."""

    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ai_provider: str = "openai"  # "openai", "openrouter", or "gemini"
    openai_model: str = "gpt-4o"
    openrouter_model: str = "openai/gpt-4o"
    gemini_model: str = "gemini-2.0-flash-exp"
    request_timeout: float = 60.0
    max_images: int = 12  # Maximum images to send to API
    base_dir: str = "data/images"
    session: Optional[Session] = None  # Optional session for loading settings from DB
    client: Optional[OpenAI] = None  # OpenAI client instance
    gemini_client: Optional[Any] = None  # Gemini model instance

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables not defined in this class

    def __init__(self, session: Optional[Session] = None, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        
        # Load settings from database if session provided
        if session:
            from services.ai_settings import AISettingsService
            ai_settings_service = AISettingsService(session)
            self.ai_provider = ai_settings_service.get_active_provider()
            api_key = ai_settings_service.get_active_api_key()

            if api_key:
                if self.ai_provider == "openai":
                    self.openai_api_key = api_key
                elif self.ai_provider == "openrouter":
                    self.openrouter_api_key = api_key
                elif self.ai_provider == "gemini":
                    self.gemini_api_key = api_key

        # Initialize client based on provider
        if self.ai_provider == "gemini":
            self.gemini_client = self._init_gemini_client()
            if not self.gemini_client:
                logger.warning(f"Gemini API key not configured - vision extraction will fail")
        else:
            self.client = self._init_client()
            if not self.client and self.ai_provider != "mock":
                logger.warning(f"AI provider '{self.ai_provider}' API key not configured - vision extraction will fail")
    
    def _init_client(self) -> Optional[OpenAI]:
        """Initialize OpenAI client based on configured provider."""
        if self.ai_provider == "openai":
            if self.openai_api_key:
                return OpenAI(api_key=self.openai_api_key)
        elif self.ai_provider == "openrouter":
            if self.openrouter_api_key:
                # OpenRouter uses OpenAI-compatible API with different base URL
                return OpenAI(
                    api_key=self.openrouter_api_key,
                    base_url="https://openrouter.ai/api/v1"
                )
        elif self.ai_provider == "mock":
            # Mock provider doesn't require a client
            return None

        return None

    def _init_gemini_client(self) -> Optional[Any]:
        """Initialize Gemini client."""
        if not GEMINI_AVAILABLE:
            logger.error("Gemini provider selected but google-generativeai not installed")
            return None

        if not self.gemini_api_key:
            logger.error("Gemini API key not configured")
            return None

        try:
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(self.gemini_model)
            logger.info(f"Initialized Gemini client with model: {self.gemini_model}")
            return model
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            return None

    def _get_model(self) -> str:
        """Get model name for current provider."""
        if self.ai_provider == "openrouter":
            return self.openrouter_model
        elif self.ai_provider == "gemini":
            return self.gemini_model
        return self.openai_model

    async def _fetch_category_aspects(self, category_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch valid aspects for an eBay category using app-level OAuth.

        Args:
            category_id: eBay leaf category ID

        Returns:
            List of aspect dictionaries with keys: name, required, aspect_mode, aspect_data_type
            Returns None if fetch fails
        """
        try:
            from integrations.ebay.app_auth import get_app_access_token
            from settings import ebay_settings
            import requests

            # Get app-level access token (doesn't require user auth)
            access_token = get_app_access_token()
            if not access_token:
                logger.error("Failed to obtain app-level access token for fetching aspects")
                return None

            # Build API URL for category aspects
            base_url = ebay_settings.get_api_base_url()
            category_tree_id = "0"  # US marketplace
            url = f"{base_url}/commerce/taxonomy/v1/category_tree/{category_tree_id}/get_item_aspects_for_category"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Language": "en-US"
            }

            params = {"category_id": category_id}

            logger.info(f"Fetching aspects for category {category_id}")
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                aspects_raw = data.get("aspects", [])

                # Normalize to simple format
                aspects = []
                for item in aspects_raw:
                    aspect_constraint = item.get("aspectConstraint", {})
                    aspects.append({
                        "name": item.get("localizedAspectName") or item.get("aspectName", ""),
                        "required": bool(aspect_constraint.get("aspectRequired", False)),
                        "aspect_mode": aspect_constraint.get("aspectMode"),
                        "aspect_data_type": item.get("aspectDataType")
                    })

                logger.info(f"Successfully fetched {len(aspects)} aspects for category {category_id}")
                return aspects
            else:
                error_msg = response.text[:200]
                logger.error(f"Failed to fetch aspects for category {category_id}: {response.status_code} - {error_msg}")
                return None

        except Exception as e:
            logger.error(f"Exception while fetching aspects for category {category_id}: {e}", exc_info=True)
            return None

    async def extract_from_images_vision(
        self, book_id: str, category_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract structured book metadata from images using GPT-4o Vision API.

        Args:
            book_id: Book identifier
            category_id: Optional eBay leaf category ID to guide extraction

        Returns:
            Dict containing extraction results:
            {
                "ok": bool,
                "errors": List[str],
                "extracted": Dict[str, Any]  # Contains all book fields
            }
        """
        try:
            # Fetch valid aspects for the category if provided
            valid_aspects = None
            if category_id:
                valid_aspects = await self._fetch_category_aspects(category_id)
                if valid_aspects:
                    logger.info(f"Fetched {len(valid_aspects)} valid aspects for category {category_id}")

            # Get image files for this book
            image_paths = self._get_image_paths(book_id)
            if not image_paths:
                return {
                    "ok": False,
                    "errors": ["No images found for book"],
                    "extracted": {}
                }

            # Limit number of images
            image_paths = image_paths[:self.max_images]

            # Read and encode images
            image_contents = []
            for img_path in image_paths:
                try:
                    with open(img_path, 'rb') as f:
                        image_data = f.read()
                    
                    # Determine MIME type
                    mime_type = self._get_mime_type(img_path)
                    
                    # Encode to base64
                    base64_image = base64.b64encode(image_data).decode('utf-8')
                    
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        }
                    })
                except Exception as e:
                    logger.error(f"Error reading image {img_path}: {e}")
                    continue

            if not image_contents:
                return {
                    "ok": False,
                    "errors": ["Failed to read any images"],
                    "extracted": {}
                }

            # Build user prompt with context and category aspects
            user_prompt = build_user_prompt(
                images_count=len(image_contents),
                known_hints={},
                valid_aspects=valid_aspects
            )

            # Prepare messages with system prompt and images
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt}
                    ] + image_contents
                }
            ]

            # Call Vision API based on provider
            if self.ai_provider == "gemini":
                # Use Gemini API
                if not self.gemini_client:
                    return {
                        "ok": False,
                        "errors": ["Gemini API key not configured. Please configure API key in Settings."],
                        "extracted": {}
                    }

                try:
                    # Prepare content for Gemini (text + images)
                    gemini_contents = [user_prompt]

                    # Add images as PIL Images for Gemini
                    from PIL import Image as PILImage
                    for img_path in image_paths:
                        try:
                            img = PILImage.open(img_path)
                            gemini_contents.append(img)
                        except Exception as e:
                            logger.error(f"Failed to load image for Gemini: {img_path} - {e}")

                    # Add system prompt as initial text
                    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

                    # Generate response
                    response_obj = self.gemini_client.generate_content(
                        [full_prompt] + [PILImage.open(p) for p in image_paths],
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.1,
                            max_output_tokens=4096,
                        )
                    )

                    response_text = response_obj.text
                    logger.debug(f"Gemini raw response: {response_text[:500]}...")

                except Exception as e:
                    logger.error(f"Gemini API call failed: {e}", exc_info=True)
                    return {
                        "ok": False,
                        "errors": [f"Gemini API error: {str(e)}"],
                        "extracted": {}
                    }

            else:
                # Use OpenAI or OpenRouter
                if not self.client:
                    if self.ai_provider == "mock":
                        error_msg = "AI provider 'mock' is not configured for vision extraction. Please configure a valid provider (openai, openrouter, or gemini) in Settings."
                    else:
                        error_msg = f"AI provider '{self.ai_provider}' API key not configured. Please configure API key in Settings."
                    return {
                        "ok": False,
                        "errors": [error_msg],
                        "extracted": {}
                    }

                model = self._get_model()
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,  # Low temperature for structured extraction
                    max_tokens=4096,  # Increased for full response
                    timeout=self.request_timeout
                )

                response_text = response.choices[0].message.content
                logger.debug(f"OpenAI/OpenRouter raw response: {response_text[:500]}...")

            # Parse JSON response
            extracted = self._parse_response(response_text)

            # Validate against Pydantic model
            try:
                # Ensure title is clipped to 80 chars before validation
                if extracted.get("ebay_title") and len(extracted["ebay_title"]) > 80:
                    extracted["ebay_title"] = extracted["ebay_title"][:80].rstrip()
                
                # Set title_char_count if not provided
                if "title_char_count" not in extracted or extracted.get("title_char_count") is None:
                    extracted["title_char_count"] = len(extracted.get("ebay_title", ""))
                
                # Validate and parse response
                enrich_result = EnrichResult.model_validate(extracted)
                
                # Ensure title_char_count is correct after validation
                enrich_result.title_char_count = len(enrich_result.ebay_title)
                
                # Convert to dict for return
                extracted_dict = enrich_result.model_dump()
                
                return {
                    "ok": True,
                    "errors": [],
                    "extracted": extracted_dict
                }
            except Exception as e:
                logger.error("Vision extraction validation failed: %s\nResponse: %s", e, (response_text or "")[:500])
                return {
                    "ok": False,
                    "errors": [f"Response validation error: {str(e)}"],
                    "extracted": extracted
                }

        except Exception as e:
            logger.error(f"Error in vision extraction for book {book_id}: {e}", exc_info=True)
            return {
                "ok": False,
                "errors": [f"Vision extraction error: {str(e)}"],
                "extracted": {}
            }

    def _get_image_paths(self, book_id: str) -> List[Path]:
        """Get all image file paths for a book."""
        image_dir = Path(self.base_dir) / book_id
        if not image_dir.exists():
            return []

        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp'}
        image_files = []

        for filename in os.listdir(image_dir):
            # Skip normalized directory
            if filename == "normalized":
                continue
            
            file_path = image_dir / filename
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                image_files.append(file_path)

        # Sort by filename for consistent ordering
        image_files.sort(key=lambda p: p.name)
        return image_files

    def _get_mime_type(self, image_path: Path) -> str:
        """Determine MIME type from file extension."""
        ext = image_path.suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.tif': 'image/tiff',
            '.tiff': 'image/tiff',
            '.bmp': 'image/bmp'
        }
        return mime_types.get(ext, 'image/jpeg')


    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON response from API."""
        import json
        
        try:
            # Remove any markdown code blocks if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nContent: {content[:500]}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return {}


    def map_to_book_fields(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map extracted EnrichResult fields to Book model fields.

        Args:
            extracted: Dict from EnrichResult.model_dump()

        Returns:
            Dict with Book model field names as keys
        """
        mapped = {}
        
        # Extract core fields
        core = extracted.get("core", {})
        
        # Direct mappings from core
        if core.get("author"):
            mapped["author"] = core["author"]
        if core.get("book_title"):
            mapped["title"] = core["book_title"]
        if core.get("publisher"):
            mapped["publisher"] = core["publisher"]
        if core.get("publication_year"):
            mapped["year"] = str(core["publication_year"])
        if core.get("language"):
            mapped["language"] = core["language"]
        if core.get("edition"):
            mapped["edition"] = core["edition"]
        if core.get("isbn13"):
            mapped["isbn13"] = core["isbn13"]
        
        # Format - join array if multiple, take first if single
        formats = core.get("format", [])
        if formats:
            mapped["format"] = formats[0] if len(formats) == 1 else ", ".join(formats)
        
        # Condition - map to ConditionGrade enum
        condition = core.get("physical_condition")
        if condition:
            from models import ConditionGrade
            condition_map = {
                "Brand New": ConditionGrade.BRAND_NEW,
                "Like New": ConditionGrade.LIKE_NEW,
                "Very Good": ConditionGrade.VERY_GOOD,
                "Good": ConditionGrade.GOOD,
                "Acceptable": ConditionGrade.ACCEPTABLE
            }
            if condition in condition_map:
                mapped["condition_grade"] = condition_map[condition]
        
        # eBay title (AI-generated SEO title)
        if extracted.get("ebay_title"):
            mapped["title_ai"] = extracted["ebay_title"]
        
        # AI description - combine overview, publication_details, and physical_condition into 3-paragraph format
        ai_desc = extracted.get("ai_description", {})
        description_parts = []
        if ai_desc.get("overview"):
            description_parts.append(ai_desc["overview"])
        if ai_desc.get("publication_details"):
            description_parts.append(ai_desc["publication_details"])
        if ai_desc.get("physical_condition"):
            description_parts.append(ai_desc["physical_condition"])
        if description_parts:
            mapped["description_ai"] = "\n\n".join(description_parts)
        
        # Build specifics_ai dict
        specifics = {}

        # ISBN-10 (store in specifics since Book model only has isbn13)
        if core.get("isbn10"):
            specifics["isbn10"] = core["isbn10"]

        # Topic, Genre - arrays
        topics = core.get("topic", [])
        if topics:
            specifics["topic"] = topics[0] if len(topics) == 1 else topics
        
        genres = core.get("genre", [])
        if genres:
            specifics["genre"] = genres[0] if len(genres) == 1 else genres
        
        # Features - array
        features = core.get("features", [])
        if features:
            specifics["features"] = features
        
        # Signed/Inscribed - store boolean and add to features
        if core.get("signed") is not None:
            specifics["signed"] = core.get("signed")
            if core.get("signed") is True:
                if "features" not in specifics:
                    specifics["features"] = []
                if "Signed" not in specifics["features"]:
                    specifics["features"].append("Signed")

        if core.get("inscribed") is not None:
            specifics["inscribed"] = core.get("inscribed")
            if core.get("inscribed") is True:
                if "features" not in specifics:
                    specifics["features"] = []
                if "Inscribed" not in specifics["features"]:
                    specifics["features"].append("Inscribed")
        
        # Additional fields from core
        if core.get("signed_by"):
            specifics["signed_by"] = core["signed_by"]
        if core.get("book_series"):
            specifics["book_series"] = core["book_series"]
        if core.get("illustrator"):
            specifics["illustrator"] = core["illustrator"]
        if core.get("literary_movement"):
            specifics["literary_movement"] = core["literary_movement"]
        if core.get("era"):
            specifics["era"] = core["era"]
        if core.get("type"):
            specifics["type"] = core["type"]
        if core.get("narrative_type"):
            specifics["narrative_type"] = core["narrative_type"]
        if core.get("intended_audience"):
            specifics["intended_audience"] = core["intended_audience"]
        if core.get("country_of_manufacture"):
            specifics["country_of_manufacture"] = core["country_of_manufacture"]
        if core.get("vintage") is not None:
            specifics["vintage"] = core.get("vintage")
            if core.get("vintage") is True:
                if "features" not in specifics:
                    specifics["features"] = []
                if "Vintage" not in specifics["features"]:
                    specifics["features"].append("Vintage")
        if core.get("ex_libris") is True:
            specifics["ex_libris"] = True
        
        if specifics:
            mapped["specifics_ai"] = specifics
        
        # Pricing hints
        pricing = extracted.get("pricing", {})
        if pricing.get("starting_price_hint"):
            mapped["price_suggested"] = float(pricing["starting_price_hint"])
        if pricing.get("floor_price_hint"):
            mapped["price_min"] = float(pricing["floor_price_hint"])

        return mapped

