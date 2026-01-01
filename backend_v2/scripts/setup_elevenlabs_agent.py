#!/usr/bin/env python3
"""
Setup ElevenLabs agent with INLINE tools (no separate tool_ids).
This ensures tools are always fresh with no caching issues.
"""

import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "https://jamify.jamiearmoordon.co.uk")
ONBOARD_TOOL_SECRET = os.getenv("ONBOARD_TOOL_SECRET")
ELEVENLABS_CUSTOM_LLM_SECRET = os.getenv("ELEVENLABS_CUSTOM_LLM_SECRET")

if not ELEVENLABS_API_KEY:
    print("ERROR: ELEVENLABS_API_KEY not set in .env")
    sys.exit(1)

if not ONBOARD_TOOL_SECRET:
    print("ERROR: ONBOARD_TOOL_SECRET not set in .env")
    sys.exit(1)

API_BASE = "https://api.elevenlabs.io"

# =============================================================================
# System Prompt - Proactive Music Discovery with Spotify Integration
# =============================================================================
SYSTEM_PROMPT = """# Who You Are
You're the Jamify DJ - a music-obsessed friend helping someone build their perfect radio station.
You have excellent taste, quick wit, and genuine curiosity about people's music preferences.

# ⚠️ CRITICAL: MINIMUM REQUIREMENTS BEFORE WRAP-UP ⚠️
**YOU MUST PLAY AT LEAST 6 SONGS before even considering wrapping up!**
**YOU MUST explore AT LEAST 3 DIFFERENT dimensions (artists, moods, eras, genres)!**
**YOU MUST have BOTH positive AND negative reactions to understand their taste!**

Count your songs. If you haven't played 6+ songs, DO NOT wrap up. Keep exploring!

WRONG after 2 songs: "I think I've got your vibe!" ❌
RIGHT after 6+ songs: "Okay, I've got a solid picture of your taste!" ✅

# CRITICAL RULE #0: CHECK SPOTIFY FIRST (MANDATORY!)
**YOUR VERY FIRST ACTION must be calling `get_spotify_context`!**

BEFORE saying ANYTHING about music:
1. Call `get_spotify_context` IMMEDIATELY
2. If has_spotify=true: Use their data! Play a song from their top tracks
3. If has_spotify=false: Ask what they've been listening to

# CRITICAL RULE #1: USE ALL YOUR TOOLS!
You have MANY tools - use them to explore different dimensions of their taste:

**REQUIRED exploration path (use at least 4 of these):**
1. ✅ Play songs from their Spotify history (if available)
2. ✅ Use `get_related_artists` to find similar artists
3. ✅ Use `get_mood_vibes` to test energy/mood preferences  
4. ✅ Use `get_era_hits` to test classic vs modern preferences
5. ✅ Use `explore_genre` to test genre boundaries
6. ✅ Use `quick_vibe_check` to get contrasting preferences

**After playing 3-4 songs in their comfort zone, BRANCH OUT:**
- "Let me test something - do you like chill vibes or more energy?" → get_mood_vibes
- "Are you into newer stuff or some classics?" → get_era_hits  
- "Let me try something completely different..." → explore_genre or quick_vibe_check

# CRITICAL RULE #2: COLLECT COMPLETE DATA
Before calling submit_onboarding_profile, you MUST have learned:

**REQUIRED fields (must have data):**
- [ ] favorite_artists (at least 3 artists they liked)
- [ ] favorite_songs (at least 3 specific song titles they loved)
- [ ] energy_preference (tested with both high and low energy songs!)
- [ ] era_preference (tested with both new and classic songs!)
- [ ] raw_context (detailed 3-4 sentence summary)

**OPTIONAL but try to discover:**
- [ ] favorite_genres
- [ ] tempo_preference
- [ ] listening_contexts (ask: "When do you usually listen - working out, chilling, driving?")
- [ ] no_go (songs/artists they clearly disliked)
- [ ] explicit_lyrics (if they react to explicit content)

# The IDEAL Conversation Flow (6-8 songs minimum!)

## Phase 1: Their World (Songs 1-3)
1. Get Spotify data → Play their top track
2. User likes it → Use get_related_artists → Play similar artist
3. User likes it → Play another from related artists
*Goal: Establish their comfort zone*

## Phase 2: Energy/Mood Exploration (Songs 4-5)  
4. Ask about mood/energy: "You seem to like [high/low] energy - let me test that..."
5. Use get_mood_vibes with OPPOSITE energy to what they've heard
*Goal: Understanding their energy range*

## Phase 3: Era/Genre Exploration (Songs 6-7)
6. Test era: "Quick question - you into newer stuff or some classics?" → get_era_hits
7. Test genre boundary: Use explore_genre with something adjacent to their taste
*Goal: Understanding their variety tolerance*

## Phase 4: Finalize (Song 8 optional)
8. If needed, use quick_vibe_check to confirm preferences
9. Ask about listening context: "When do you usually listen - working out, relaxing, driving?"
10. THEN wrap up with complete submit_onboarding_profile

# Your Vibe
- Warm and natural. Like chatting with a friend, not an interview.
- Keep responses SHORT - 1-2 sentences max. This is voice conversation!
- Actually ASK about their preferences between songs
- React to their reactions - if they love something, dig deeper!

# CRITICAL RULE #3: PLAY FIRST, WAIT, THEN TALK! (MOST IMPORTANT!)
**NEVER say anything like "Let me play..." or "Have you heard..." BEFORE calling play_song_preview!**
**The tool call MUST come FIRST, with NO speech before it!**
**The play_song_preview tool will play a 12-second preview window and then return, allowing you to ask for feedback.**
**After play_song_preview returns (after ~12 seconds), you can immediately speak - no need for wait_for_listening.**

WRONG (never do this):
- Say "Let me play Doorman for you!" → then call play_song_preview ❌
- Say "Have you heard this?" → then call play_song_preview ❌

CORRECT (always do this):
1. SILENTLY call play_song_preview(artist_name="...", track_title="...") 
2. WAIT for the tool to return (it plays ~12 seconds then returns)
3. ONLY THEN speak: "You feeling this?" or "What do you think?"

The tool blocks for ~12 seconds, then returns so you can ask for feedback while the preview may still be playing.

# CRITICAL RULE #4: DON'T MAKE SWEEPING CONCLUSIONS
One song rejection = they don't like THAT SONG
NOT = they don't like the entire genre/era/energy level

Need reactions to 6+ songs to understand their taste properly.

# TOOL REFERENCE

## ALWAYS USE FIRST
- **get_spotify_context**: Call IMMEDIATELY when conversation starts

## PRIMARY TOOLS  
- **search_artist_music**: When user mentions an artist
- **search_tracks**: When user mentions artist + song title
- **get_related_artists**: Find similar artists (use after they like something!)
- **play_song_preview**: MUST call this for user to hear music! Plays full 30s preview and blocks until complete.

## EXPLORATION TOOLS (Use these to diversify!)
- **get_mood_vibes**: Test energy/mood (chill, energetic, melancholic, happy, focused)
- **get_era_hits**: Test decade preferences (90s, 80s, 2000s, recent, classic)
- **explore_genre**: Deep dive into a genre
- **quick_vibe_check**: Get contrasting pairs for quick preference checks

## FINAL TOOL
- **submit_onboarding_profile**: ONLY after 6+ songs and complete data collection!

# When To Wrap Up Checklist
Before saying "I've got your vibe", verify:
☐ Played at least 6 songs
☐ Got at least 2-3 positive reactions
☐ Got at least 1-2 negative/neutral reactions (important for understanding dislikes!)
☐ Tested different energy levels
☐ Tested at least one genre/era outside their comfort zone
☐ Asked about listening context
☐ Have at least 3 favorite artists identified
☐ Have at least 3 favorite song titles identified

If ANY of these are missing, KEEP EXPLORING!

# Submit Profile Notes
When calling submit_onboarding_profile, include:
- favorite_songs: Specific song TITLES they loved (need at least 3!)
- favorite_artists: Artists they reacted positively to (need at least 3!)
- favorite_genres: Inferred from reactions
- energy_preference: "high_energy" | "low_energy" | "mixed" (MUST test both!)
- tempo_preference: "fast" | "slow" | "mixed"
- era_preference: "new_releases" | "classics" | "mixed" (MUST test both!)
- listening_contexts: When/where they listen (ASK them!)
- no_go: What they clearly disliked
- raw_context: Detailed 3-4 sentence summary of their complete taste profile
- display_name: What they want to be called (ask if not obvious)

# Rules
- NEVER say "onboarding" - say "getting your vibe"
- NEVER read JSON or technical output  
- NEVER wrap up after only 2-3 songs!
- If preview fails: "Let me try another..." and pick different track
- If they seem unsure: Play something, don't ask questions
- ALWAYS branch out after 3 songs in the same lane
"""

FIRST_MESSAGE = "Hey! I'm your DJ for today - Ready to start your onboarding journey?"


# =============================================================================
# Inline Tool Definitions (webhook tools defined directly in agent config)
# =============================================================================

def get_inline_tools():
    """Get all tools as inline webhook configs."""
    return [
        # 0. Get Spotify Context (CALL THIS FIRST!)
        {
            "type": "webhook",
            "name": "get_spotify_context",
            "description": "MANDATORY FIRST CALL! Get the user's Spotify listening data. Call this IMMEDIATELY when conversation starts, BEFORE saying anything about music. Returns has_spotify (boolean), top_artists, top_tracks, and favorite_genres. If has_spotify=true, use this data to start playing their favorite music right away!",
            "response_timeout_secs": 10,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/spotify-context",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "dynamic_variable": "user_id"
                        }
                    },
                    "required": ["user_id"]
                }
            }
        },
        # 1. Submit Onboarding Profile
        {
            "type": "webhook",
            "name": "submit_onboarding_profile",
            "description": "Submit the user's music preferences and complete onboarding. Call this when you have gathered enough information about their music taste. Needs at least 3 favorite artists/songs.",
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/onboard/submit",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "dynamic_variable": "user_id"
                        },
                        "display_name": {
                            "type": "string",
                            "description": "What the user wants to be called"
                        },
                        "favorite_genres": {
                            "type": "array",
                            "description": "List of music genres the user enjoys",
                            "items": {"type": "string", "description": "A genre name"}
                        },
                        "favorite_artists": {
                            "type": "array",
                            "description": "List of artists the user mentioned liking",
                            "items": {"type": "string", "description": "An artist name"}
                        },
                        "favorite_songs": {
                            "type": "array",
                            "description": "IMPORTANT: List of specific song TITLES the user loves (e.g. 'Blinding Lights', 'Bad Guy')",
                            "items": {"type": "string", "description": "A song title (not artist name)"}
                        },
                        "no_go": {
                            "type": "array",
                            "description": "Artists or genres to avoid",
                            "items": {"type": "string", "description": "An artist or genre to avoid"}
                        },
                        "explicit_lyrics": {
                            "type": "string",
                            "description": "Whether explicit lyrics are okay: ok, avoid, or depends"
                        },
                        "dj_personality": {
                            "type": "string",
                            "description": "The DJ personality the user prefers"
                        },
                        "energy_preference": {
                            "type": "string",
                            "description": "Energy preference INFERRED from preview reactions: high_energy (loves bangers), low_energy (prefers chill), mixed"
                        },
                        "tempo_preference": {
                            "type": "string",
                            "description": "Tempo preference INFERRED from preview reactions: fast (upbeat), slow (laid-back), mixed"
                        },
                        "era_preference": {
                            "type": "string",
                            "description": "Era preference INFERRED from preview reactions: new_releases (recent hits), classics (older/throwback), mixed"
                        },
                        "listening_contexts": {
                            "type": "array",
                            "description": "When/where user listens to music: workout, focus, party, commute, relaxing, cooking, etc.",
                            "items": {"type": "string", "description": "Context name"}
                        },
                        "raw_context": {
                            "type": "string",
                            "description": "2-3 sentences capturing their full vibe naturally"
                        },
                        "demographics": {
                            "type": "object",
                            "description": "Only if explicitly mentioned (age range, location)",
                            "properties": {
                                "age_range": {
                                    "type": "string",
                                    "description": "User's age range if mentioned"
                                },
                                "location": {
                                    "type": "string",
                                    "description": "User's location if mentioned"
                                }
                            }
                        }
                    },
                    "required": ["user_id", "favorite_genres", "favorite_artists", "energy_preference", "tempo_preference", "era_preference"]
                }
            }
        },
        # 2. Get Related Artists
        {
            "type": "webhook",
            "name": "get_related_artists",
            "description": "Get similar artists when the user likes someone. Good for staying in the 'comfort zone'.",
            "response_timeout_secs": 30,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/related-artists",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "artist_name": {
                            "type": "string",
                            "description": "The artist name to find related artists for"
                        },
                        "artist_id": {
                            "type": "integer",
                            "description": "Optional Deezer artist ID if known"
                        }
                    },
                    "required": ["artist_name"]
                }
            }
        },
        # 3. Get Mood Vibes
        {
            "type": "webhook",
            "name": "get_mood_vibes",
            "description": "Get tracks matching a specific mood (party, chill, focus, workout, sad, happy). Use this to test energy levels.",
            "response_timeout_secs": 30,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/mood-search",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "mood": {
                            "type": "string",
                            "description": "The mood to search for (e.g. 'chill', 'party', 'gym')"
                        },
                        "genres": {
                            "type": "array",
                            "description": "Optional genre hints",
                            "items": {"type": "string", "description": "A genre name"}
                        }
                    },
                    "required": ["mood"]
                }
            }
        },
        # 4. Get Era Hits
        {
            "type": "webhook",
            "name": "get_era_hits",
            "description": "Get top tracks from a specific decade/era (80s, 90s, 2000s, 2010s). Use this to test era preferences.",
            "response_timeout_secs": 30,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/era-search",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "era": {
                            "type": "string",
                            "description": "The decade to search (e.g. '80s', '90s', '2000s')"
                        },
                        "genre": {
                            "type": "string",
                            "description": "Optional genre filter"
                        }
                    },
                    "required": ["era"]
                }
            }
        },
        # 5. Explore Genre
        {
            "type": "webhook",
            "name": "explore_genre",
            "description": "Get popular tracks for a specific genre. Use this to branch out or test new genres.",
            "response_timeout_secs": 30,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/genre-explore",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "genre": {
                            "type": "string",
                            "description": "Genre to explore: pop, rock, hip-hop, electronic, jazz, etc."
                        },
                        "subgenre": {
                            "type": "string",
                            "description": "Optional subgenre"
                        }
                    },
                    "required": ["genre"]
                }
            }
        },
        # 6. Search Artist Music
        {
            "type": "webhook",
            "name": "search_artist_music",
            "description": "Search for a specific artist's top tracks if you don't have a specific song name.",
            "response_timeout_secs": 30,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/artist-search",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "artist_name": {
                            "type": "string",
                            "description": "The artist name"
                        }
                    },
                    "required": ["artist_name"]
                }
            }
        },
        # 7. Search Tracks
        {
            "type": "webhook",
            "name": "search_tracks",
            "description": "Search for tracks with a precise query. Use Deezer query syntax like artist:\"Name\" track:\"Title\".",
            "response_timeout_secs": 30,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/track-search",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., artist:\"Skepta\" track:\"Shutdown\")"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "How many results to return (1-20)"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        # 8. Quick Vibe Check
        {
            "type": "webhook",
            "name": "quick_vibe_check",
            "description": "Get contrasting track pairs to quickly narrow down preferences. Use early in conversation.",
            "response_timeout_secs": 30,
            "api_schema": {
                "url": f"{BACKEND_BASE_URL}/api/v1/deezer/vibe-check",
                "method": "POST",
                "request_headers": {
                    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
                },
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "dimension": {
                            "type": "string",
                            "description": "What to test: energy, era, mood"
                        }
                    },
                    "required": ["dimension"]
                }
            }
        },
        # 9. Wait for Listening (Client Tool)
        {
            "type": "client",
            "name": "wait_for_listening",
            "description": "Pause to give the user time to listen to the preview before asking for feedback.",
            "expects_response": True,
            "response_timeout_secs": 35,
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "How many seconds to wait (3-30)"
                    }
                },
                "required": ["seconds"]
            }
        },
        # 10. Play Song Preview (Client Tool - MUST CALL THIS TO PLAY MUSIC!)
        {
            "type": "client",
            "name": "play_song_preview",
            "description": "REQUIRED to play music! Call this tool to play a song preview. The user CANNOT hear any music unless you call this tool. This tool will play a 12-second preview window and then return, allowing you to ask for feedback. The preview may continue playing in the background after the tool returns.",
            "expects_response": True,  # Block conversation until client responds
            "response_timeout_secs": 20,  # 20 seconds max wait (12s preview + buffer)
            "parameters": {
                "type": "object",
                "properties": {
                    "artist_name": {
                        "type": "string",
                        "description": "The artist name"
                    },
                    "track_title": {
                        "type": "string",
                        "description": "The title of the track to play"
                    }
                },
                "required": ["artist_name", "track_title"]
            }
        }
    ]

# =============================================================================
# Agent Configuration
# =============================================================================

def get_agent_config():
    """Build the complete agent configuration with inline tools."""
    return {
        "name": "Jamify Onboarding",
        "conversation_config": {
            "tts": {
                "voice_id": "aD6riP1btT197c6dACmy",  # A friendly, warm voice
                "model_id": "eleven_turbo_v2",
                "stability": 0.5,
                "similarity_boost": 0.8,
                "speed": 1.0
            },
            "asr": {
                "quality": "high",
                "provider": "elevenlabs"
            },
            "turn": {
                "turn_timeout": 10.0,
                "silence_end_call_timeout": 30.0
            },
            "agent": {
                "first_message": FIRST_MESSAGE,
                "language": "en",
                "prompt": {
                    "prompt": SYSTEM_PROMPT,
                    "llm": "gemini-2.0-flash-001",  # Latest supported Gemini on ElevenLabs
                    "temperature": 0.5,  # Lower for more consistent reasoning
                    "tools": get_inline_tools()  # Inline tools here!
                },
                "dynamic_variables": {
                    "dynamic_variable_placeholders": {
                        "user_id": "placeholder_user_id"
                    }
                }
            }
        }
    }


# =============================================================================
# API Functions
# =============================================================================

def create_agent(agent_config):
    """Create a new agent."""
    print("   Creating NEW agent...")
    response = httpx.post(
        f"{API_BASE}/v1/convai/agents/create",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        },
        json=agent_config,
        timeout=60.0
    )
    
    if response.status_code != 200:
        print(f"ERROR: Failed to create agent: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    agent_id = data["agent_id"]
    print(f"   OK: Agent created: {agent_id}")
    return agent_id


def update_agent(agent_id, agent_config):
    """Update an existing agent."""
    print(f"   Updating EXISTING agent {agent_id}...")
    
    # PATCH endpoint
    response = httpx.patch(
        f"{API_BASE}/v1/convai/agents/{agent_id}",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        },
        json=agent_config,
        timeout=60.0
    )
    
    if response.status_code != 200:
        print(f"ERROR: Failed to update agent: {response.status_code}")
        print(response.text)
        # Fallback to create if update fails (e.g. 404)
        if response.status_code == 404:
            print("   WARN: Agent not found, creating new one...")
            return create_agent(agent_config)
        sys.exit(1)
            
    data = response.json()
    # API might return different structure on patch, but we just need to know it succeeded
    print("   OK: Agent updated successfully")
    return agent_id


def update_env_file(agent_id: str):
    """Update .env file with new agent ID."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_path = os.path.abspath(env_path)
    
    if not os.path.exists(env_path):
        print(f"   WARN: .env file not found at {env_path}")
        return
    
    with open(env_path, "r") as f:
        lines = f.readlines()
    
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("ELEVENLABS_ONBOARD_AGENT_ID="):
            new_lines.append(f"ELEVENLABS_ONBOARD_AGENT_ID={agent_id}\n")
            updated = True
        else:
            new_lines.append(line)
    
    if not updated:
        new_lines.append(f"ELEVENLABS_ONBOARD_AGENT_ID={agent_id}\n")
    
    with open(env_path, "w") as f:
        f.writelines(new_lines)
    
    print(f"   OK: Updated .env with ELEVENLABS_ONBOARD_AGENT_ID={agent_id}")


def main():
    print("=" * 60)
    print("Jamify Onboarding Agent Setup (Inline Tools)")
    print("=" * 60)
    print(f"\nBackend URL: {BACKEND_BASE_URL}")
    
    agent_config = get_agent_config()
    
    # Check for existing agent ID
    existing_agent_id = os.getenv("ELEVENLABS_ONBOARD_AGENT_ID")
    
    print("\n" + "=" * 60)
    if existing_agent_id:
        print(f"Found existing agent ID: {existing_agent_id}")
        agent_id = update_agent(existing_agent_id, agent_config)
    else:
        print("No existing agent ID found.")
        agent_id = create_agent(agent_config)
    print("=" * 60)
    
    # Update .env (ensure it's set/verified)
    print("\n" + "=" * 60)
    print("Updating .env file...")
    print("=" * 60)
    update_env_file(agent_id)
    
    # Summary
    print("\n" + "=" * 60)
    print("OK: Setup complete!")
    print("=" * 60)
    print(f"   Agent ID: {agent_id}")
    print(f"   Tools: {len(get_inline_tools())} inline tools available")
    print("\nDashboard:")
    print(f"   https://elevenlabs.io/app/agents/{agent_id}")
    print("\nFeatures:")
    print("   - Natural conversation flow (Improved Prompt)")
    print("   - Spotify Integration (accesses real listening data!)")
    print("   - Deezer music discovery (Mood, Era, Genre, Vibe)")
    print("   - Song preview playback (fresh URLs)")
    print("   - Related artist suggestions")


if __name__ == "__main__":
    main()
