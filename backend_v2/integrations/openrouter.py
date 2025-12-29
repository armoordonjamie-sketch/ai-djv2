"""OpenRouter API client for Gemini 2.5 Flash LLM calls.

Ported from backend/integrations/openrouter.py with adaptations for:
- PreferenceBundle-based personalization
- Per-user agent settings
- Prompt template injection
- LLM trace storage with user_id/mood_id

Evidence: Implementing Phase 4 of implementation_plan.md
"""
import httpx
import json
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from backend_v2.config import (
    OPENROUTER_API_KEY,
    THINKING_BUDGET_TRACK,
    THINKING_BUDGET_TRANSITION,
    THINKING_BUDGET_SPEECH,
)

if TYPE_CHECKING:
    from backend_v2.services.preference_bundle import PreferenceBundle

logger = logging.getLogger("ai-dj.openrouter")


# =============================================================================
# LLM Output Validation Helpers
# =============================================================================

def validate_track_selection_response(
    parsed: Optional[Dict[str, Any]],
    valid_uuids: Optional[List[str]] = None
) -> bool:
    """Validate track selection response structure."""
    if not parsed:
        return False
    
    selected_uuid = parsed.get('selected_uuid')
    if not isinstance(selected_uuid, str) or len(selected_uuid.strip()) == 0:
        return False
    
    if valid_uuids is not None and selected_uuid not in valid_uuids:
        logger.warning(f"LLM selected UUID '{selected_uuid}' not in valid list")
        return False
    
    return True


def validate_transition_plan_response(parsed: Optional[Dict[str, Any]]) -> bool:
    """Validate transition plan response structure."""
    if not parsed or not isinstance(parsed, dict):
        return False
    
    transition_type = parsed.get('transition_type')
    if not isinstance(transition_type, str) or not transition_type:
        return False
    
    mix_length = parsed.get('mix_length_bars')
    if not isinstance(mix_length, (int, float)):
        return False
    if int(mix_length) not in {8, 16, 32}:
        return False
    
    start_pos = parsed.get('start_position_b_seconds')
    if not isinstance(start_pos, (int, float)):
        return False
    if start_pos < 0:
        return False
    
    return True


# =============================================================================
# Profile Context Helper
# =============================================================================

def build_profile_context(bundle: "PreferenceBundle") -> str:
    """Build a concise profile summary for LLM prompts.
    
    Extracts structured profile data from bundle.profile and formats
    it for inclusion in AI prompts.
    
    Args:
        bundle: User's preference bundle with profile
        
    Returns:
        Formatted string with user profile info
    """
    lines = []
    
    if bundle.profile:
        # User name
        if bundle.profile.display_name:
            lines.append(f"User: {bundle.profile.display_name}")
        
        # Music preferences
        if bundle.profile.favorite_genres:
            lines.append(f"Favorite Genres: {', '.join(bundle.profile.favorite_genres[:5])}")
        
        if bundle.profile.favorite_artists:
            lines.append(f"Favorite Artists: {', '.join(bundle.profile.favorite_artists[:5])}")
        
        if bundle.profile.favorite_songs:
            lines.append(f"Favorite Songs: {', '.join(bundle.profile.favorite_songs[:3])}")
        
        # Hard constraints
        if bundle.profile.no_go:
            lines.append(f"AVOID (user hates): {', '.join(bundle.profile.no_go)}")
        
        if not bundle.profile.allows_explicit():
            lines.append("AVOID explicit lyrics")
        
        # DJ personality preference
        personality_labels = {
            "casual_funny": "casual/funny style",
            "minimal_talk": "minimal talk preferred",
            "hype_energetic": "hype/energetic style",
            "light_roast": "light roasting welcome",
            "more_talk_between_songs": "chatty/talkative style",
        }
        if bundle.profile.dj_personality in personality_labels:
            lines.append(f"DJ Style: {personality_labels[bundle.profile.dj_personality]}")
    
    # Fallback to legacy context if no profile data
    if not lines and bundle.context and bundle.context.parsed_json:
        pj = bundle.context.parsed_json
        if pj.get("display_name"):
            lines.append(f"User: {pj['display_name']}")
        if pj.get("favorite_genres"):
            lines.append(f"Favorite Genres: {', '.join(pj['favorite_genres'][:5])}")
        if pj.get("favorite_artists"):
            lines.append(f"Favorite Artists: {', '.join(pj['favorite_artists'][:5])}")
        if pj.get("no_go"):
            lines.append(f"AVOID: {', '.join(pj['no_go'])}")
    
    return "\n".join(lines)


# =============================================================================
# OpenRouter Client
# =============================================================================

class OpenRouterClient:
    """Async client for OpenRouter API (Gemini 2.5 Flash).
    
    Adapted for multi-user backend with:
    - PreferenceBundle integration for personalization
    - Per-user agent settings (thinking_budget, temperature)
    - Prompt template injection
    - LLM trace storage
    """
    
    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = "google/gemini-2.5-flash"
        self.model_lite = "google/gemini-2.5-flash-lite"
        
        if not self.api_key:
            logger.warning("OpenRouter API key not configured")
            self.enabled = False
        else:
            self.enabled = True
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jamify.uk",
            "X-Title": "Jamify AI DJ"
        }
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_budget: Optional[int] = None,
        json_mode: bool = False,
        search_web: bool = False,
        use_lite_model: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Call Gemini 2.5 Flash via OpenRouter."""
        if not self.enabled:
            logger.debug("OpenRouter client disabled")
            return None
        
        try:
            model = self.model_lite if use_lite_model else self.model
            if search_web:
                model += ":online"
            
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            if thinking_budget:
                payload["max_reasoning_tokens"] = thinking_budget
            
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
                # Add JSON instruction to system message
                if messages and messages[0]["role"] == "system":
                    if isinstance(messages[0]["content"], str):
                        messages[0]["content"] += "\n\nRespond with valid JSON only."
            
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
                    choice = data['choices'][0]
                    content = choice.get('message', {}).get('content', '')
                    
                    result = {
                        'content': content,
                        'model': data.get('model'),
                        'usage': data.get('usage', {}),
                        'finish_reason': choice.get('finish_reason'),
                    }
                    
                    if json_mode:
                        try:
                            result['parsed'] = json.loads(content)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse JSON: {e}")
                            result['parsed'] = None
                    
                    return result
                
                logger.error(f"No choices in response: {data}")
                return None
        
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter API error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
            return None
    
    async def estimate_song_features(
        self,
        artist: str,
        title: str,
        genres: List[str]
    ) -> Optional[Dict[str, float]]:
        """Estimate audio features (energy, valence) using LLM knowledge."""
        system_prompt = """You are an audio analysis expert.
Estimate the audio features for the given song on a scale of 0.0 to 1.0.

Features:
- Energy: Intensity and activity (0.0=calm, 1.0=intense)
- Valence: Musical positiveness (0.0=sad/depressed, 1.0=happy/euphoric)
- Danceability: Suitability for dancing (0.0=concerto, 1.0=club banger)
- Acousticness: 1.0 = purely acoustic, 0.0 = electronic/amplified

Also estimate Tempo (BPM).

Respond with JSON only:
{
  "energy": 0.8,
  "valence": 0.5,
  "danceability": 0.7,
  "acousticness": 0.1,
  "tempo": 120
}"""

        user_prompt = f"Song: {title} by {artist}\nGenres: {', '.join(genres)}"
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = await self.chat_completion(
                messages=messages,
                temperature=0.1,
                json_mode=True,
            )

            if not response:
                return None

            if response.get("parsed"):
                data = response["parsed"]
                return {
                    "energy": float(data.get("energy", 0.5)),
                    "valence": float(data.get("valence", 0.5)),
                    "danceability": float(data.get("danceability", 0.5)),
                    "acousticness": float(data.get("acousticness", 0.5)),
                    "tempo": float(data.get("tempo", 120)),
                }

            content = response.get("content", "")
            if content:
                import json
                import re

                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    return {
                        "energy": float(data.get("energy", 0.5)),
                        "valence": float(data.get("valence", 0.5)),
                        "danceability": float(data.get("danceability", 0.5)),
                        "acousticness": float(data.get("acousticness", 0.5)),
                        "tempo": float(data.get("tempo", 120)),
                    }
        except Exception as e:
            logger.error(f"Feature estimation failed: {e}")

        return None

    async def generate_song_suggestion(
        self,
        bundle: "PreferenceBundle",
        prev_song: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate a song suggestion to acquire (when library is insufficient).
        
        Args:
            bundle: User's preference bundle
            prev_song: Previous song context
            
        Returns:
            Dict with artist, title, rationale
        """
        # Get agent settings
        thinking_budget = bundle.get_agent_setting(
            "track_selector", "thinking_budget", THINKING_BUDGET_TRACK
        )
        temperature = bundle.get_agent_setting(
            "track_selector", "temperature", 0.9  # Higher temp for creative suggestions
        )
        
        # Build profile context from structured onboarding data
        profile_context = build_profile_context(bundle)
        
        # Build history + feedback context
        recent_tracks = [
            f"{h.artist} - {h.title}"
            for h in bundle.history.recent_tracks[:5]  # Reduced from 10 for token efficiency
            if h.artist and h.title
        ]
        recent_artists = [a for a in bundle.history.recent_artists[:5] if a]  # Reduced from 10

        likes_section = ""
        if bundle.feedback.recent_likes[:3]:
            likes_examples = "\n".join([
                f"- {l.artist} - {l.title}" + (f" ({l.reason})" if l.reason else "")
                for l in bundle.feedback.recent_likes[:3]
                if l.artist and l.title
            ])
            if likes_examples:
                likes_section = f"USER LIKES (lean toward these vibes):\n{likes_examples}\n"

        dislikes_section = ""
        if bundle.feedback.recent_dislikes[:3]:
            dislikes_examples = "\n".join([
                f"- {d.artist} - {d.title}" + (f" ({d.reason})" if d.reason else "")
                for d in bundle.feedback.recent_dislikes[:3]
                if d.artist and d.title
            ])
            if dislikes_examples:
                dislikes_section = f"USER DISLIKES (avoid these and similar):\n{dislikes_examples}\n"

        history_section = ""
        if recent_tracks:
            history_section = f"RECENTLY PLAYED (DO NOT SUGGEST THESE):\n- " + "\n- ".join(recent_tracks) + "\n"

        recent_artists_section = ""
        if recent_artists:
            recent_artists_section = f"RECENT ARTISTS (prefer variety):\n- " + "\n- ".join(recent_artists) + "\n"
        
        # Log the context being used
        logger.info(
            f"Song suggestion using profile: {profile_context[:100]}... "
            f"History tracks: {len(recent_tracks)}, artists: {len(recent_artists)}"
        )
        
        system_prompt = f"""You are an expert DJ building a setlist.

Target Mood: {bundle.mood.name} (Energy: {bundle.mood.energy_target:.1f}, Valence: {bundle.mood.valence_target:.1f})
Genres: {', '.join(bundle.mood.genres)}

{profile_context}
{likes_section}{dislikes_section}{history_section}{recent_artists_section}
Suggest ONE real song that fits this vibe perfectly.
It can be a classic hit, a deep cut, or a new release.
You are NOT restricted to any library. Pick the best song in the world for this moment.
Prefer a fresh, adventurous pick (deep cut, emerging artist, or adjacent-genre gem) over obvious staples unless the user's likes indicate otherwise.

Respond with JSON:
{{
  "artist": "Artist Name",
  "title": "Song Title",
  "rationale": "Reason for choice"
}}"""

        prev_section = ""
        if prev_song:
            prev_section = f"Previous Song: {prev_song.get('artist')} - {prev_song.get('title')}\n"
            
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{prev_section}Suggest the perfect next track to download."}
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=True,
            search_web=True, # Allow web search to verify song exists
        )
        
        if result and result.get('parsed'):
            parsed = result['parsed']
            if parsed.get('artist') and parsed.get('title'):
                return parsed
        
        return None

    async def generate_track_selection(
        self,
        bundle: "PreferenceBundle",
        candidates: List[Dict[str, Any]],
        prev_song: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate track selection using PreferenceBundle personalization.
        
        Args:
            bundle: User's preference bundle
            candidates: Pre-scored candidate songs (top N from deterministic scoring)
            prev_song: Previous song for transition context
            
        Returns:
            Dict with selected_uuid, rationale, or None
        """
        # Get agent settings
        thinking_budget = bundle.get_agent_setting(
            "track_selector", "thinking_budget", THINKING_BUDGET_TRACK
        )
        temperature = bundle.get_agent_setting(
            "track_selector", "temperature", 0.7
        )
        
        # Build personalization context
        persona_section = ""
        if bundle.mood_profile.summary_text:
            persona_section = f"\nLEARNED USER PREFERENCES:\n{bundle.mood_profile.summary_text}\n"
        
        # Few-shot examples from feedback
        likes_section = ""
        if bundle.feedback.recent_likes[:3]:
            likes_examples = "\n".join([
                f"- {l.artist} - {l.title}" + (f" ({l.reason})" if l.reason else "")
                for l in bundle.feedback.recent_likes[:3]
                if l.artist and l.title
            ])
            likes_section = f"\nUSER LIKES (prefer similar):\n{likes_examples}\n"
        
        dislikes_section = ""
        if bundle.feedback.recent_dislikes[:3]:
            dislikes_examples = "\n".join([
                f"- {d.artist} - {d.title}" + (f" ({d.reason})" if d.reason else "")
                for d in bundle.feedback.recent_dislikes[:3]
                if d.artist and d.title
            ])
            dislikes_section = f"\nUSER DISLIKES (avoid these and similar):\n{dislikes_examples}\n"
        
        # Build history context
        recent_section = ""
        recent_tracks = [
            f"{h.artist} - {h.title}"
            for h in bundle.history.recent_tracks[:10]
            if h.artist and h.title
        ]
        if recent_tracks:
            recent_section = f"\nRECENT PLAYS (STRICTLY AVOID REPEATING THESE):\n- " + "\n- ".join(recent_tracks) + "\n"
        elif bundle.history.recent_plays[:10]:
            # Fallback to UUIDs if no titles available
            recent_section = f"\nRECENT PLAYS (avoid repeating IDs):\n{bundle.history.recent_plays[:10]}\n"

        recent_artists_section = ""
        if bundle.history.recent_artists[:10]:
            recent_artists_section = (
                "\nRECENT ARTISTS (prefer variety):\n- "
                + "\n- ".join(bundle.history.recent_artists[:10])
                + "\n"
            )
        
        # Apply prompt template if exists
        base_system = bundle.get_prompt_template("track_selection_system")
        if not base_system:
            base_system = """You are an expert DJ selecting the perfect next track.

SELECTION CRITERIA (priority order):
1. Musical compatibility: tempo (±10 BPM preferred), energy flow
2. User personalization: respect mood targets, genre preferences
3. Lyrical/thematic coherence with previous track
4. Avoid recently played songs
5. Emotional arc: manage energy intentionally
6. Novelty: if candidates are close, favor a less obvious or more adventurous pick"""
        
        system_prompt = f"""{base_system}

TARGET MOOD: {bundle.mood.name}
- Energy target: {bundle.mood.energy_target:.1f} (0=calm, 1=energetic)
- Valence target: {bundle.mood.valence_target:.1f} (0=sad, 1=happy)
- Preferred genres: {', '.join(bundle.mood.genres)}
{persona_section}{likes_section}{dislikes_section}{recent_section}{recent_artists_section}
USER CONTEXT:
{bundle.context.raw_text[:500]}"""

        # Format candidates (compact JSON for token efficiency)
        candidates_text = json.dumps([
            {
                "uuid": c.get("uuid"),
                "artist": c.get("artist"),
                "title": c.get("title"),
                "score": round(c.get("score", 0.5), 2),
                "energy": round(c.get("features", {}).get("energy") or 0, 2),
                "tempo": int(c.get("features", {}).get("tempo") or 0),
            }
            for c in candidates[:10]  # Reduced from 15 for token efficiency
        ], separators=(',', ':'))  # Compact JSON
        
        prev_section = ""
        if prev_song:
            prev_section = f"""
Previous Song (just played):
- Artist: {prev_song.get('artist', 'Unknown')}
- Title: {prev_song.get('title', 'Unknown')}
- Energy: {prev_song.get('features', {}).get('energy', 'N/A')}
- Tempo: {prev_song.get('features', {}).get('tempo', 'N/A')} BPM
"""
        
        user_prompt = f"""{prev_section}
Available Candidates (pre-scored, higher = better fit):
{candidates_text}

Select the best next track. Respond with JSON:
{{
  "selected_uuid": "uuid-here",
  "rationale": "Why this track fits the vibe and user preferences"
}}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=True,
        )
        
        # Validate response
        if result and result.get('parsed'):
            valid_uuids = [c.get('uuid') for c in candidates]
            if validate_track_selection_response(result['parsed'], valid_uuids):
                return result
            else:
                logger.warning("Invalid track selection response, falling back to top candidate")
        
        return result
    
    async def generate_transition_plan(
        self,
        bundle: "PreferenceBundle",
        song_a: Dict[str, Any],
        song_b: Dict[str, Any],
        recent_transition_types: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate transition plan between two songs.
        
        Args:
            bundle: User's preference bundle
            song_a: Current song with features
            song_b: Next song with features
            
        Returns:
            Dict with transition_type, mix_length_bars, start_position_b_seconds
        """
        thinking_budget = bundle.get_agent_setting(
            "transition_planner", "thinking_budget", THINKING_BUDGET_TRANSITION
        )
        temperature = bundle.get_agent_setting(
            "transition_planner", "temperature", 0.4
        )
        
        system_prompt = """You are an expert DJ creating smooth radio transitions.

TRANSITION TYPES AVAILABLE:
- crossfade: Standard blend, works for similar tempo (within 5-10 BPM)
- eq_blend: EQ-style crossfade, professional sound
- filter_sweep: LPF sweep, good for energy changes
- bass_swap: Frequency split, best for tight tempo matches (within ~3 BPM)
- quick_cut: Hard switch, use for large BPM gaps (>20 BPM)
- vinyl_stop: Turntable brake effect on outgoing track (use sparingly)
- loop_mix: Loop last bar of outgoing while bringing in incoming
- drop_mix: Quick bass cut on outgoing, then drop to incoming

OUTPUT FORMAT (JSON):
{
  "transition_type": "crossfade",
  "mix_length_bars": 16,
  "start_position_b_seconds": 0.0,
  "rationale": "Brief explanation"
}

RULES:
- mix_length_bars must be 8, 16, or 32
- start_position_b_seconds: where to start Song B (0 = beginning)
- Vary transition types for interest, don't always use the same one
- Avoid repeating the same transition type back-to-back"""
        
        def format_track(track: Dict, label: str) -> str:
            features = track.get('features', {})
            lines = [f"{label}:"]
            lines.append(f"  Title: {track.get('title', 'Unknown')}")
            lines.append(f"  Artist: {track.get('artist', 'Unknown')}")
            if features.get('tempo'):
                lines.append(f"  BPM: {features['tempo']:.1f}")
            if features.get('energy') is not None:
                lines.append(f"  Energy: {features['energy']:.2f}")
            if features.get('key') is not None:
                lines.append(f"  Key: {features['key']}")
            if track.get('duration_sec'):
                lines.append(f"  Duration: {track['duration_sec']:.1f}s")
            return "\n".join(lines)
        
        recent_line = ""
        if recent_transition_types:
            recent_line = (
                "\nRecent transitions (avoid repeating): "
                + ", ".join(recent_transition_types[-3:])
            )

        user_prompt = f"""
{format_track(song_a, "Song A (current)")}

{format_track(song_b, "Song B (next)")}

{recent_line}

Generate the transition plan:"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=True,
        )
        
        if result and result.get('parsed'):
            if validate_transition_plan_response(result['parsed']):
                return result
            else:
                # Provide default fallback
                logger.warning("Invalid transition plan, using crossfade default")
                result['parsed'] = {
                    "transition_type": "crossfade",
                    "mix_length_bars": 16,
                    "start_position_b_seconds": 0.0,
                    "rationale": "Default crossfade fallback"
                }
        
        return result
    
    async def generate_dj_intro_speech(
        self,
        bundle: "PreferenceBundle",
        song_info: Dict[str, Any],
        banter_history: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate DJ intro speech for set opening.
        
        Args:
            bundle: User's preference bundle
            song_info: First song info (title, artist)
            banter_history: Recent DJ speeches to avoid repetition
            
        Returns:
            Dict with text, tone
        """
        thinking_budget = bundle.get_agent_setting(
            "speech_writer", "thinking_budget", THINKING_BUDGET_SPEECH
        )
        temperature = bundle.get_agent_setting(
            "speech_writer", "temperature", 0.9
        )
        
        # Build history avoidance
        history_section = ""
        if banter_history:
            history_section = f"\nRECENT BANTER (don't repeat):\n- " + "\n- ".join(banter_history[-5:])
        
        # Extract mood-specific context for unique intros
        mood_keywords = []
        example_artists = []
        intro_style = bundle.mood.dj_personality
        
        # Get mood metadata if available
        try:
            import json
            if hasattr(bundle.mood, 'vibe_keywords_json') and bundle.mood.vibe_keywords_json:
                mood_keywords = json.loads(bundle.mood.vibe_keywords_json)
            if hasattr(bundle.mood, 'example_artists_json') and bundle.mood.example_artists_json:
                example_artists = json.loads(bundle.mood.example_artists_json)
            if hasattr(bundle.mood, 'intro_personality') and bundle.mood.intro_personality:
                intro_style = bundle.mood.intro_personality
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"Could not parse mood metadata: {e}")
        
        # Build mood context section
        mood_context = f"""
MOOD: {bundle.mood.name}
MOOD ENERGY: {bundle.mood.energy_target:.1f} (0=calm, 1=intense)
MOOD VIBE: {bundle.mood.valence_target:.1f} (0=melancholic, 1=euphoric)"""
        
        if mood_keywords:
            mood_context += f"\nMOOD KEYWORDS: {', '.join(mood_keywords[:4])}"
        
        if example_artists:
            mood_context += f"\nEXAMPLE ARTISTS FOR THIS MOOD: {', '.join(example_artists[:3])}"
        
        # Map intro personalities to speech styles
        intro_style_map = {
            "upbeat_welcoming": "Warm and upbeat. Make the listener feel energized and ready for the day.",
            "hyped_energetic": "HYPED and PUMPED! Get them FIRED UP! Use exclamation marks and energy!",
            "calm_soothing": "Calm, gentle, and soothing. Like a warm embrace. Speak softly.",
            "celebratory_wild": "Celebratory and WILD! This is a PARTY! Let's GO! Maximum enthusiasm!",
            "mysterious_intimate": "Mysterious and intimate. Whisper-like. Create an atmosphere of late-night introspection.",
            "minimal": "Brief and understated. 1-2 sentences max.",
            "chill": "Relaxed and friendly. 2-3 sentences.",
            "chatty": "Engaging and energetic. 2-4 sentences with personality.",
        }
        intro_style_desc = intro_style_map.get(intro_style, intro_style_map["chill"])
        
        # Use mood personality
        personality_map = {
            "minimal": "Brief and understated. 1-2 sentences max.",
            "chill": "Relaxed and friendly. 2-3 sentences.",
            "chatty": "Engaging and energetic. 2-4 sentences with personality.",
        }
        personality_desc = personality_map.get(
            bundle.mood.dj_personality, 
            personality_map["chill"]
        )
        
        # Apply prompt template if exists
        base_system = bundle.get_prompt_template("dj_intro_system")
        if not base_system:
            base_system = f"""You are a witty, personable DJ starting a new set.

PERSONALITY STYLE: {bundle.mood.dj_personality.upper()}
{personality_desc}

{mood_context}

INTRO STYLE FOR THIS MOOD: {intro_style_desc}

USER CONTEXT:
{bundle.context.raw_text[:300]}
{history_section}

GUIDELINES:
- Warm greeting, set the mood
- Reference the first song naturally
- Emphasize the mood's unique vibe ({bundle.mood.name})
- Match the intro style for this specific mood
- Avoid cheesy radio clichés
- Don't use technical jargon (BPM, key, etc.)
- Make this intro sound DIFFERENT from other moods"""
        
        user_prompt = f"""
First Song:
- Title: {song_info.get('title', 'Unknown')}
- Artist: {song_info.get('artist', 'Unknown')}

Generate a DJ intro. Respond with JSON:
{{
  "text": "Your intro speech here",
  "tone": "excited"
}}"""
        
        messages = [
            {"role": "system", "content": base_system},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=True,
        )
        
        # Post-process to sanitize
        if result and result.get('parsed') and result['parsed'].get('text'):
            result['parsed']['text'] = self._sanitize_tts_output(result['parsed']['text'])
        
        return result
    
    async def generate_dj_speech(
        self,
        bundle: "PreferenceBundle",
        context: Dict[str, Any],
        banter_history: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate transition DJ speech.
        
        Args:
            bundle: User's preference bundle  
            context: Current context (prev_song, next_song, transition_type)
            banter_history: Recent speeches to avoid repetition
            
        Returns:
            Dict with text, tone
        """
        thinking_budget = bundle.get_agent_setting(
            "speech_writer", "thinking_budget", THINKING_BUDGET_SPEECH
        )
        temperature = bundle.get_agent_setting(
            "speech_writer", "temperature", 0.9
        )
        
        history_section = ""
        if banter_history:
            history_section = f"\nRECENT BANTER (don't repeat):\n- " + "\n- ".join(banter_history[-5:])
        
        # Use profile data for DJ personality
        dj_style = bundle.get_dj_personality()
        display_name = bundle.get_display_name()
        
        # Build profile context for additional personalization
        profile_context = build_profile_context(bundle)
        
        # Map personality styles to speech guidance
        personality_map = {
            "minimal_talk": "Very brief. 1 sentence max.",
            "chill": "Relaxed. 1-2 sentences.",
            "chatty": "Engaging. 2-3 sentences with personality.",
            "casual_funny": "Casual and funny. 2-3 witty sentences.",
            "calm_radio": "Calm radio host style. 1-2 sentences.",
            "hype_energetic": "Energetic! Hyped up! 2-3 punchy sentences.",
            "light_roast": "Witty with light roasting. 2-3 sentences.",
            "more_talk_between_songs": "Chatty and conversational. 3-4 sentences.",
        }
        personality_desc = personality_map.get(dj_style, personality_map["casual_funny"])
        
        # Roast guidance based on personality
        roast_guidance = ""
        if dj_style == "light_roast" and display_name:
            roast_guidance = f"\nFeel free to playfully roast {display_name} occasionally."
        
        base_system = bundle.get_prompt_template("dj_speech_system")
        if not base_system:
            listener_line = f"Listener: {display_name}\n" if display_name else ""
            base_system = f"""You are a witty DJ creating short spoken transitions.

PERSONALITY: {dj_style.upper()}
{personality_desc}{roast_guidance}
{listener_line}{history_section}

{profile_context}

GUIDELINES:
- Natural, conversational
- Reference songs by name/artist
- No technical jargon (BPM, key, crossfade, etc.)
- Don't be cheesy"""
        
        # Sanitize context to remove technical fields
        safe_context = self._sanitize_speech_context(context)
        
        user_prompt = f"""
Context:
{json.dumps(safe_context, indent=2)}

Generate DJ speech. Respond with JSON:
{{
  "text": "Your speech here",
  "tone": "humorous"
}}"""
        
        messages = [
            {"role": "system", "content": base_system},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=True,
        )
        
        if result and result.get('parsed') and result['parsed'].get('text'):
            result['parsed']['text'] = self._sanitize_tts_output(result['parsed']['text'])
        
        return result
    
    def _sanitize_speech_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Remove technical metadata from context."""
        technical_fields = {
            'tempo', 'bpm', 'key', 'camelot_code', 'energy', 'danceability',
            'valence', 'beats', 'downbeats', 'cue_in_seconds', 'cue_out_seconds',
            'duration_seconds', 'loudness', 'ffmpeg_filter', 'mix_length_bars',
            'start_position_b_seconds', 'song_a_start_sec', 'song_b_start_sec',
            'features', 'score'
        }
        
        def clean_dict(d: Dict) -> Dict:
            return {k: v for k, v in d.items() if k.lower() not in technical_fields}
        
        sanitized = {}
        for key, value in context.items():
            if key.lower() in technical_fields:
                continue
            if isinstance(value, dict):
                sanitized[key] = clean_dict(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _sanitize_tts_output(self, text: str) -> str:
        """Remove technical terms from TTS output."""
        forbidden_patterns = [
            r'\b\d{2,3}\s*(bpm|beats?\s*per\s*minute)\b',
            r'\b(bpm|beats?\s*per\s*minute)\s*of?\s*\d{2,3}\b',
            r'\b(key\s+of\s+)?[A-G](#|b)?\s*(major|minor|m)\b',
            r'\b\d{1,2}[AB]\b',
            r'\bcamelot\s*(wheel|code|key)?\b',
            r'\b(crossfade|eq[_\s]?blend|bass[_\s]?swap|filter[_\s]?sweep|echo[_\s]?out|vinyl[_\s]?stop|quick[_\s]?cut|loop[_\s]?mix|drop[_\s]?mix|filtergraph|ffmpeg|atrim)\b',
            r'\benergy\s*(score|level|rating)?\s*:?\s*\d+(\.\d+)?\b',
            r'\b(danceability|valence)\s*:?\s*\d+(\.\d+)?\b',
            r'\b\d+(\.\d+)?\s*(db|decibels?|lufs)\b',
        ]
        
        result = text
        for pattern in forbidden_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        # Clean up artifacts
        result = re.sub(r'\s{2,}', ' ', result)
        result = re.sub(r',\s*,', ',', result)
        result = re.sub(r',\s*\.', '.', result)
        result = result.strip()
        
        return result


# =============================================================================
# LLM Trace Storage
# =============================================================================

async def store_llm_trace(
    db,  # AsyncSession
    user_id: str,
    mood_id: Optional[str],
    session_id: str,
    agent_name: str,
    prompt: str,
    response: str,
    model: str,
    thinking_budget: Optional[int] = None,
):
    """Store LLM interaction trace in database."""
    from backend_v2.models.existing import LLMTrace
    
    trace = LLMTrace(
        session_id=session_id,
        user_id=user_id,
        mood_id=mood_id,
        agent_name=agent_name,
        prompt=prompt[:10000],  # Truncate for storage
        response=response[:10000],
        model=model,
        thinking_budget=thinking_budget,
        created_at=datetime.utcnow().isoformat() + "Z",
    )
    db.add(trace)
    await db.flush()
    
    logger.debug(f"Stored LLM trace for {agent_name}")


# =============================================================================
# Singleton
# =============================================================================

_openrouter_client: Optional[OpenRouterClient] = None


def get_openrouter_client() -> OpenRouterClient:
    """Get or create global OpenRouter client."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = OpenRouterClient()
    return _openrouter_client

