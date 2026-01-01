"""OpenRouter API client for analyzing Spotify data with structured output."""
import httpx
import json
import logging
from typing import Dict, Any, Optional

from schemas import get_enrichment_schema

logger = logging.getLogger("spotify-test.openrouter")


class OpenRouterClient:
    """Client for OpenRouter API with structured output support."""
    
    def __init__(self, api_key: str):
        """Initialize OpenRouter client.
        
        Args:
            api_key: OpenRouter API key
        """
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = "google/gemini-2.5-flash"
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jamify.uk",
            "X-Title": "Spotify Onboarding Enrichment"
        }
    
    async def analyze_spotify_data(self, spotify_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze Spotify data and extract preferences and profile summary.
        
        Args:
            spotify_data: Aggregated Spotify data (profile, playlists, tracks, artists)
            
        Returns:
            Dictionary with 'music_preferences' and 'profile_summary' keys, or None on error
        """
        schema = get_enrichment_schema()
        
        # Build prompt
        prompt = self._build_analysis_prompt(spotify_data)
        
        messages = [
            {
                "role": "system",
                "content": "You are a music analysis expert. Analyze Spotify user data and extract their music preferences and listening profile. Respond with valid JSON matching the provided schema."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "spotify_enrichment",
                    "strict": True,
                    "schema": schema
                }
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get('choices') and len(data['choices']) > 0:
                    content = data['choices'][0]['message']['content']
                    # Parse JSON response
                    if isinstance(content, str):
                        result = json.loads(content)
                    else:
                        result = content
                    
                    return result
                else:
                    logger.error("No choices in OpenRouter response")
                    return None
                    
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter HTTP error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenRouter JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in OpenRouter call: {e}")
            return None
    
    def _build_analysis_prompt(self, spotify_data: Dict[str, Any]) -> str:
        """Build comprehensive analysis prompt from Spotify data.
        
        Args:
            spotify_data: Aggregated Spotify data with all time ranges and recently played
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "Analyze the following comprehensive Spotify user data and extract detailed insights:",
            "",
            "1. Favorite Artists: Identify top favorite artists across all time ranges, including their genres, popularity, and why they might be favorites.",
            "2. Favorite Songs: Identify favorite songs from top tracks across all time ranges, including artist, album, and why they're favorites.",
            "3. Last Listened To: Analyze recently played tracks and identify patterns in what they're listening to now.",
            "4. Top Played: Organize top tracks and artists by time range (short_term=last 4 weeks, medium_term=last 6 months, long_term=all time).",
            "5. User Profile Summary: Create a comprehensive profile including listener type, music discovery style, and listening patterns.",
            "6. Playlist Analysis: Analyze playlists to identify themes, favorite playlists, and playlist creation style.",
            "7. Music Preferences: Extract genres, energy levels, moods, tempo ranges, and decade preferences.",
            "8. Listening Habits: Analyze when they listen, how often, playlist vs album preference, discovery methods, and repeat behavior.",
            "9. Genres Analysis: Identify primary genres, genre diversity, and how genres evolve across time ranges.",
            "10. Mood Analysis: Identify dominant moods, mood patterns, and how mood affects listening choices.",
            "",
            "Spotify Data:",
            json.dumps(spotify_data, indent=2),
            "",
            "Provide a comprehensive, detailed analysis that captures the user's complete music profile and preferences."
        ]
        
        return "\n".join(prompt_parts)

