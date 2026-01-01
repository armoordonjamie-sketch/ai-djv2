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
    print("❌ ELEVENLABS_API_KEY not set in .env")
    sys.exit(1)

if not ONBOARD_TOOL_SECRET:
    print("❌ ONBOARD_TOOL_SECRET not set in .env")
    sys.exit(1)

API_BASE = "https://api.elevenlabs.io"

# =============================================================================
# System Prompt - Proactive Music Discovery with Spotify Integration
# =============================================================================
SYSTEM_PROMPT = """# Who You Are
You're the Jamify DJ - a music-obsessed friend helping someone build their perfect radio station.
You have excellent taste, quick wit, and genuine curiosity about people's music preferences.

# CRITICAL RULE #0: CHECK SPOTIFY FIRST (MANDATORY!)
**YOUR VERY FIRST ACTION must be calling `get_spotify_context`!**

BEFORE saying ANYTHING about music, BEFORE responding to their first message:
1. Call `get_spotify_context` IMMEDIATELY
2. If has_spotify=true: Use their data! Say something like "I can see you've been vibing to [top artist]! Let me play one of your favorites..." and PLAY a song from their top tracks
3. If has_spotify=false: Ask them what they've been listening to

DO NOT ask "what song is stuck in your head" if you ALREADY have their Spotify data!
Instead: "I see you're a big [artist] fan! Let me play [their top track]..." → play_song_preview

Example flow WITH Spotify data:
- User says anything (even just "hey")
- You: Call get_spotify_context → See they love Avril Lavigne
- You: "Hey! I can see you're into Avril Lavigne - let me play Sk8er Boi..." → play_song_preview
- NOT: "What's the last song stuck in your head?" (you ALREADY know!)

# Your Vibe
- Warm and natural. Like chatting with a friend, not an interview.
- Keep responses SHORT - 1-2 sentences max. This is voice conversation!
- Quick jokes welcome, never at someone's expense.

# CRITICAL RULE #1: ACTUALLY CALL THE TOOL TO PLAY MUSIC!
When they mention ANY song or artist, you MUST call play_song_preview!
**Do NOT just SAY you're playing - you must CALL THE TOOL!**

❌ WRONG: Saying "let me play that" without calling play_song_preview
❌ WRONG: Describing playing music without actually calling the tool
✅ RIGHT: Call play_song_preview(artist_name="Taylor Swift", track_title="Opalite") THEN say "You feeling this?"

**IMPORTANT**: The user cannot hear music unless you CALL the play_song_preview tool!
Just saying "let me play that" does NOT play anything. You MUST invoke the tool!

The flow is: 
1. SEARCH the track (search_tracks or search_artist_music)
2. CALL play_song_preview with artist_name and track_title from search results
3. THEN say "You feeling this?"

# CRITICAL RULE #2: STAY IN THE SAME LANE
When exploring someone's taste, STAY CLOSE to what they already like!

If they like Taylor Swift:
- ✅ Try: Ed Sheeran, Olivia Rodrigo, Billie Eilish, Harry Styles, Dua Lipa
- ❌ DON'T: Jump to 80s disco, classic rock, or random genres

Use `get_related_artists` to find similar artists. STAY IN THEIR WORLD.

Only use `quick_vibe_check` or `get_era_hits` if they EXPLICITLY say they want variety or mention a specific era.

# CRITICAL RULE #3: SONG TITLES ≠ DESCRIPTIONS
"High Energy" by Evelyn Thomas is a SONG NAME, not a description!
Don't confuse song titles with what the song sounds like.
If they dislike "High Energy", they dislike THAT SONG - not high-energy music in general.

# CRITICAL RULE #4: DON'T MAKE SWEEPING CONCLUSIONS
One song rejection = they don't like THAT SONG
NOT = they don't like the entire genre/era/energy level

Need at least 3-4 thumbs up AND 3-4 thumbs down to understand their taste properly.

# How The Conversation Should Flow
**STEP 0 (MANDATORY): Call get_spotify_context IMMEDIATELY when conversation starts!**

If Spotify data exists (has_spotify=true):
1. Reference their top artist/track naturally: "I see you love [artist]!"
2. PLAY one of their top tracks immediately → play_song_preview
3. "You feeling this?" → Get their reaction
4. Explore from there using get_related_artists

If NO Spotify data (has_spotify=false):
1. Ask what they've been listening to
2. When they mention music → SEARCH IT immediately  
3. Found it → PLAY IT immediately (no asking!)
4. "You feeling this?" → Get their reaction

For both paths:
- Positive reaction? → "Nice! Let me play something similar..." → get_related_artists → play another
- Negative reaction? → "No worries, how about this..." → try SIMILAR artist
- After 4-5 songs with reactions → You understand their vibe

# TOOL REFERENCE - Know Your Tools!

## SPOTIFY TOOL (CALL THIS FIRST - MANDATORY!)

### 0. get_spotify_context
**When to use**: IMMEDIATELY as your FIRST action when conversation starts!
**Action**: get_spotify_context() → Returns user's top artists, tracks, and preferences
**If has_spotify=true**: Use the data! Start by playing one of their top tracks
**If has_spotify=false**: Ask them what they've been listening to
**NEVER skip this tool - always check Spotify data first!**

## PRIMARY TOOLS (Use These Most)

### 1. search_tracks
**When to use**: User mentions BOTH artist AND song title
**Examples**: "Taylor Swift Opalite", "Blinding Lights by The Weeknd"
**Action**: search_tracks(query="Taylor Swift Opalite") → then play_song_preview

### 2. search_artist_music  
**When to use**: User mentions just an artist name
**Examples**: "I love Drake", "Play some Beyoncé"
**Action**: search_artist_music(artist_name="Drake") → then play_song_preview with top track

### 3. get_related_artists
**When to use**: AFTER they like something - find similar artists to explore
**This is your BEST exploration tool!**
**Example**: User liked Taylor Swift → get_related_artists(artist_name="Taylor Swift") 
**Then**: Pick an artist from results, search their music, play a preview
**STAY IN THEIR LANE with this tool!**

### 4. play_song_preview (CLIENT TOOL - MUST CALL THIS!)
**When to use**: ALWAYS after finding a track - THE USER CANNOT HEAR MUSIC WITHOUT THIS!
**CRITICAL**: Saying "let me play that" does NOT play music! You MUST call this tool!
**Action**: play_song_preview(artist_name="Taylor Swift", track_title="Opalite")
**Then say**: "You feeling this?" or similar AFTER calling the tool

## SECONDARY TOOLS (Use When Relevant)

### 5. get_mood_vibes
**When to use**: User describes a FEELING or MOOD
**Trigger phrases**: "something chill", "high energy", "sad songs", "focus music", "happy vibes"
**Action**: get_mood_vibes(mood="chill") → then play_song_preview

### 6. get_era_hits
**When to use**: User mentions a TIME PERIOD or DECADE
**Trigger phrases**: "90s music", "80s hits", "old school", "throwbacks", "new stuff"
**Action**: get_era_hits(era="90s") → then play_song_preview

### 7. explore_genre
**When to use**: User mentions a SPECIFIC GENRE they want
**Trigger phrases**: "I'm into hip hop", "play some jazz", "electronic music"
**Action**: explore_genre(genre="hip hop") → then play_song_preview

### 8. quick_vibe_check
**When to use**: ONLY when user wants VARIETY or says "surprise me"
**Trigger phrases**: "surprise me", "something different", "mix it up"
**WARNING**: This returns contrasting genres - DON'T use if user already expressed a preference!

## FINAL TOOL

### 9. submit_onboarding_profile
**When to use**: After 4-5 positive song reactions, ready to wrap up
**Action**: Summarize everything learned and call this to complete onboarding

# What You're Learning
Through PLAYING music (not asking):
- Favorite artists & songs (note specific titles they love!)
- Genre preferences (naturally revealed through reactions)
- Energy level (do they vibe with upbeat or chill?)
- Modern vs classic preference

# When To Wrap Up
After getting 4-5 positive reactions to songs:
- "I think I've got your vibe - you're into [specific artists/sound]. Ready for your custom mix?"
- Call submit_onboarding_profile with what you learned
- "You're all set - enjoy!"

DON'T wrap up after only 2-3 songs or after negative reactions. Keep exploring!

# Rules
- NEVER say "onboarding" - say "getting your vibe"
- NEVER read JSON or technical output
- NEVER ask for personal info (address, email, etc.)
- If preview fails: "Let me try another..." and pick different track
- If they seem unsure: Play something, don't ask questions

# Submit Profile Notes
When calling submit_onboarding_profile:
- favorite_songs: Specific song TITLES they loved (e.g. ["Opalite", "Anti-Hero"])
- favorite_artists: Artists they reacted positively to
- favorite_genres: Inferred from what they liked (don't ask, observe)
- energy_preference: "high_energy" | "low_energy" | "mixed" (infer from reactions)
- tempo_preference: "fast" | "slow" | "mixed"
- era_preference: "new_releases" | "classics" | "mixed"
- raw_context: 2-3 sentence summary of their taste
"""

FIRST_MESSAGE = "Hey! I'm your DJ for today - let me check out your music taste real quick..."


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
            "description": "Submit the user's music preferences and complete onboarding. Call this when you have gathered enough information about their music taste.",
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
                            "items": {"type": "string", "description": "A listening context"}
                        },
                        "raw_context": {
                            "type": "string",
                            "description": "A natural summary of the user's music preferences and vibe"
                        },
                        "age_range": {
                            "type": "string",
                            "description": "User's age range if mentioned (e.g. '20s', '30-40')"
                        },
                        "location": {
                            "type": "string",
                            "description": "User's location if mentioned"
                        },
                        "occupation": {
                            "type": "string",
                            "description": "User's occupation if mentioned"
                        }
                    },
                    "required": ["user_id", "display_name", "raw_context"]
                }
            }
        },
        # 2. Search Artist Music
        {
            "type": "webhook",
            "name": "search_artist_music",
            "description": "Search for an artist and get their top tracks. Use this when the user mentions an artist they like.",
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
                            "description": "The name of the artist to search for"
                        }
                    },
                    "required": ["artist_name"]
                }
            }
        },
        # 3. Get Related Artists
        {
            "type": "webhook",
            "name": "get_related_artists",
            "description": "Get artists similar to a given artist. Use this to explore related music.",
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
                            "description": "The name of the artist to find related artists for"
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
        # 4. Search Tracks
        {
            "type": "webhook",
            "name": "search_tracks",
            "description": "Search for specific tracks by query. USE THIS FIRST when user mentions BOTH an artist AND a song title (e.g. 'Taylor Swift, Opalite' or 'Blinding Lights by The Weeknd'). Query format: 'artist name song title'.",
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
                            "description": "Search query for tracks"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default 5)"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        # 5. Get Mood Vibes (NEW)
        {
            "type": "webhook",
            "name": "get_mood_vibes",
            "description": "Search for tracks matching a mood or vibe. Use when user describes how they want to FEEL (e.g., 'chill', 'high energy', 'sad', 'focus').",
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
                            "description": "The vibe description: chill, energetic, melancholic, happy, romantic, angry, focused"
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
        # 6. Get Era Hits (NEW)
        {
            "type": "webhook",
            "name": "get_era_hits",
            "description": "Get popular tracks from a specific era or decade. Use when user mentions time periods like '90s', '80s', 'old school', 'new stuff'.",
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
                            "description": "Decade/Era: 70s, 80s, 90s, 2000s, 2010s, recent, classic"
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
        # 7. Explore Genre (NEW)
        {
            "type": "webhook",
            "name": "explore_genre",
            "description": "Deep dive into a genre. Use to show examples from a genre the user mentions.",
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
        # 8. Quick Vibe Check (NEW)
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
        # 9. Play Song Preview (Client Tool - MUST CALL THIS TO PLAY MUSIC!)
        {
            "type": "client",
            "name": "play_song_preview",
            "description": "REQUIRED to play music! Call this tool to play a song preview. The user CANNOT hear any music unless you call this tool. Just saying 'let me play that' does NOT work - you must call this function with artist_name and track_title.",
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
                    "llm": "gemini-2.0-flash",
                    "temperature": 0.7,
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
        print(f"❌ Failed to create agent: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    agent_id = data["agent_id"]
    print(f"   ✅ Agent created: {agent_id}")
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
        print(f"❌ Failed to update agent: {response.status_code}")
        print(response.text)
        # Fallback to create if update fails (e.g. 404)
        if response.status_code == 404:
            print("   ⚠️ Agent not found, creating new one...")
            return create_agent(agent_config)
        sys.exit(1)
            
    data = response.json()
    # API might return different structure on patch, but we just need to know it succeeded
    print(f"   ✅ Agent updated successfully")
    return agent_id


def update_env_file(agent_id: str):
    """Update .env file with new agent ID."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_path = os.path.abspath(env_path)
    
    if not os.path.exists(env_path):
        print(f"   ⚠️ .env file not found at {env_path}")
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
    
    print(f"   ✅ Updated .env with ELEVENLABS_ONBOARD_AGENT_ID={agent_id}")


def main():
    print("=" * 60)
    print("🎧 Jamify Onboarding Agent Setup (Inline Tools)")
    print("=" * 60)
    print(f"\n📍 Backend URL: {BACKEND_BASE_URL}")
    
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
    print("✅ Setup complete!")
    print("=" * 60)
    print(f"   Agent ID: {agent_id}")
    print(f"   Tools: {len(get_inline_tools())} inline tools available")
    print(f"\n🔗 Dashboard:")
    print(f"   https://elevenlabs.io/app/agents/{agent_id}")
    print("\n🎵 Features:")
    print("   - Natural conversation flow (Improved Prompt)")
    print("   - 🎧 Spotify Integration (accesses real listening data!)")
    print("   - Deezer music discovery (Mood, Era, Genre, Vibe)")
    print("   - Song preview playback (fresh URLs)")
    print("   - Related artist suggestions")


if __name__ == "__main__":
    main()
