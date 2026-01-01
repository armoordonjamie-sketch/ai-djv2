"""ElevenLabs TTS API client for DJ speech synthesis.

Ported from backend/integrations/elevenlabs.py with per-user settings support.

Evidence: Implementing Phase 4 of implementation_plan.md
"""
import httpx
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING

from backend_v2.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL_ID,
    TTS_DIR,
)

if TYPE_CHECKING:
    from backend_v2.services.preference_bundle import PreferenceBundle

logger = logging.getLogger("ai-dj.elevenlabs")


class ElevenLabsClient:
    """Async client for ElevenLabs TTS API.
    
    Supports per-user voice/model settings via PreferenceBundle.
    """
    
    def __init__(self):
        self.api_key = ELEVENLABS_API_KEY
        self.voice_id = ELEVENLABS_VOICE_ID
        self.model_id = ELEVENLABS_MODEL_ID
        self.base_url = "https://api.elevenlabs.io/v1"
        
        if not self.api_key:
            logger.warning("ElevenLabs API key not configured")
            self.enabled = False
        else:
            self.enabled = True
        
        self.headers = {
            "xi-api-key": self.api_key or "",
            "Content-Type": "application/json",
        }
        
        # Ensure TTS directory exists
        Path(TTS_DIR).mkdir(parents=True, exist_ok=True)
    
    async def synthesize_speech(
        self,
        text: str,
        output_filename: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> Optional[str]:
        """Synthesize speech from text.
        
        Args:
            text: Text to synthesize
            output_filename: Optional custom filename
            voice_id: Override voice ID (for per-user settings)
            model_id: Override model ID (for per-user settings)
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity boost (0-1)
            
        Returns:
            Path to saved audio file, or None on error
        """
        if not self.enabled:
            logger.debug("ElevenLabs client disabled")
            return None
        
        if not text or not text.strip():
            logger.warning("Empty text passed to TTS")
            return None
        
        try:
            # Use overrides or defaults
            use_voice_id = voice_id or self.voice_id
            use_model_id = model_id or self.model_id
            
            # Generate filename if not provided
            if output_filename is None:
                output_filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
            
            output_path = os.path.join(TTS_DIR, output_filename)
            
            payload = {
                "text": text,
                "model_id": use_model_id,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                },
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/text-to-speech/{use_voice_id}",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                
                # Save audio file
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"TTS synthesized: {output_path} ({len(text)} chars)")
                return output_path
        
        except httpx.HTTPError as e:
            logger.error(f"ElevenLabs TTS error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected TTS error: {e}")
            return None
    
    async def synthesize_from_bundle(
        self,
        text: str,
        bundle: "PreferenceBundle",
        output_filename: Optional[str] = None,
    ) -> Optional[str]:
        """Synthesize speech using per-user settings from bundle.
        
        Args:
            text: Text to synthesize
            bundle: User's preference bundle
            output_filename: Optional custom filename
            
        Returns:
            Path to saved audio file, or None on error
        """
        # Get per-user TTS settings
        voice_id = bundle.get_agent_setting("tts", "voice_id", None)
        model_id = bundle.get_agent_setting("tts", "model_id", None)
        stability = bundle.get_agent_setting("tts", "stability", 0.5)
        similarity = bundle.get_agent_setting("tts", "similarity_boost", 0.75)
        
        return await self.synthesize_speech(
            text=text,
            output_filename=output_filename,
            voice_id=voice_id,
            model_id=model_id,
            stability=stability,
            similarity_boost=similarity,
        )
    
    async def get_voice_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the configured voice."""
        if not self.enabled:
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/voices/{self.voice_id}",
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"ElevenLabs voice info error: {e}")
            return None


# =============================================================================
# Singleton
# =============================================================================

_elevenlabs_client: Optional[ElevenLabsClient] = None


def get_elevenlabs_client() -> ElevenLabsClient:
    """Get or create global ElevenLabs client."""
    global _elevenlabs_client
    if _elevenlabs_client is None:
        _elevenlabs_client = ElevenLabsClient()
    return _elevenlabs_client
