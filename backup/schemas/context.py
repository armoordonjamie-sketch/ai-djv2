"""Pydantic schemas for user contexts."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class ContextCreate(BaseModel):
    """Create context request."""
    name: str = Field(..., min_length=1, max_length=100)
    raw_text: Optional[str] = None


class ContextUpdate(BaseModel):
    """Update context request."""
    raw_text: Optional[str] = None
    parsed_json: Optional[str] = None


class ContextResponse(BaseModel):
    """Context response."""
    id: str
    name: str
    raw_text: Optional[str]
    parsed_json: Optional[str]
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
