"""Pydantic schemas for agent settings and prompt templates."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# Agent Settings
class AgentSettingsUpdate(BaseModel):
    """Update agent settings request."""
    settings_json: str  # JSON string


class AgentSettingsResponse(BaseModel):
    """Agent settings response."""
    id: str
    agent_name: str
    settings_json: Optional[str]
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Prompt Templates
class PromptTemplateCreate(BaseModel):
    """Create/update prompt template request."""
    scope: str = Field("global", pattern=r'^(global|mood)$')
    mood_id: Optional[str] = None
    role: str = Field("system", pattern=r'^(system|user)$')
    template_text: str


class PromptTemplateResponse(BaseModel):
    """Prompt template response."""
    id: str
    name: str
    scope: str
    mood_id: Optional[str]
    role: str
    template_text: str
    version: int
    is_active: bool
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
