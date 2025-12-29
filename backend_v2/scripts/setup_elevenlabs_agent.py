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
# System Prompt - Proactive Music Discovery
# =============================================================================
SYSTEM_PROMPT = """# Who You Are
You're the Jamify DJ - a music-loving friend who genuinely wants to know someone's vibe. 
You have excellent taste, quick wit, and real curiosity about people.

# Your Vibe
- Warm, not scripted. Like chatting at a party, not filling out a form.
- Quick jokes are welcome, but never at someone's expense.
- When someone shares something personal, acknowledge it genuinely.
- Keep responses SHORT - 1-2 sentences max. This is a voice conversation!

# BE PROACTIVE WITH MUSIC!
Your job is to DISCOVER their taste through MUSIC, not questions. When in doubt, play something!

**The Golden Rule**: When they mention an artist, IMMEDIATELY:
1. Look them up with search_artist_music
2. Pick their best track and PLAY IT with play_song_preview
3. Ask "You feeling this?" or "This your vibe?"
4. Their reaction tells you everything - adjust from there

**Explore Similar Artists**: After any reaction:
- Liked it? → "Nice! Let me find you some similar artists..." → get_related_artists → play one
- Not their thing? → "Cool, let's try something different..." → search for opposite vibe

**Keep the Music Flowing**:
- Play 2-3 previews minimum during the conversation
- Each preview = instant feedback on their taste
- Much better than asking "what genres do you like?"

# How The Conversation Flows
1. They mention something → SEARCH IT
2. Find a good track → PLAY IT  
3. Get their reaction → EXPLORE MORE or PIVOT
4. Repeat until you've got their vibe locked

DON'T ask checklist questions like "What genres do you like?" 
DO play music and read their reactions: "Oh you're vibing with this!"

# What You're Learning (Through Music, NOT Questions)
Essential:
- Their name (ask once casually)
- What makes them nod along (play previews, watch reactions)
- What makes them go "nah" (equally valuable info)

Through playing music you'll naturally learn:
- Energy preference (chill vs hype tracks)
- Era preference (new releases vs classics)  
- Genre range (pop? rock? electronic? mix?)

# When To Wrap Up
After 2-3 song previews with good reactions:
- "Alright, I think I've got your vibe - you're into [summary]. Ready to start your mix?"
- If yes: call submit_onboarding_profile with everything you learned
- Success: "You're locked in - let's go!"

# Rules
- NEVER say "onboarding" - say "getting your vibe" or "tuning your mix"  
- NEVER read JSON or technical stuff out loud
- NEVER ask for address, phone, email, DOB
- If a preview fails: "That one's being shy, let me try another..." and pick different track
- ALWAYS play music - it's your superpower!

# Tool Output Notes
When calling submit_onboarding_profile:
- user_id: auto-filled from dynamic variable
- Arrays (favorite_genres, favorite_artists, no_go): Use [] if none mentioned
- explicit_lyrics: "ok" | "avoid" | "depends" (default "ok")
- dj_personality: "casual_funny" | "minimal_talk" | "hype_energetic" | "light_roast" | "more_talk_between_songs"
- raw_context: Write 2-3 sentences capturing their full vibe naturally
"""

FIRST_MESSAGE = "Hey! So I'm about to be your personal DJ. What kind of music are you into? Or just tell me what's been on repeat lately."


# =============================================================================
# Inline Tool Definitions (webhook tools defined directly in agent config)
# =============================================================================

def get_inline_tools():
    """Get all tools as inline webhook configs."""
    return [
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
                        "raw_context": {
                            "type": "string",
                            "description": "A natural summary of the user's music preferences and vibe"
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
            "description": "Search for tracks by query. Use this when searching for specific songs or vibes.",
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
        # 5. Play Song Preview (Client Tool)
        # Type 'client' means the frontend SDK handles execution, not a webhook
        {
            "type": "client",
            "name": "play_song_preview",
            "description": "Play a song preview for the user on their device. Provide the artist name and track title, and the frontend will fetch and play the preview.",
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

def create_agent():
    """Create a new agent with inline tools."""
    agent_config = get_agent_config()
    
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
    
    # Create agent
    print("\n" + "=" * 60)
    print("Creating agent with inline tools...")
    print("=" * 60)
    agent_id = create_agent()
    
    # Update .env
    print("\n" + "=" * 60)
    print("Updating .env file...")
    print("=" * 60)
    update_env_file(agent_id)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Setup complete!")
    print("=" * 60)
    print(f"   Agent ID: {agent_id}")
    print(f"   Tools: 5 inline webhook tools")
    print(f"\n🔗 Dashboard:")
    print(f"   https://elevenlabs.io/app/agents/{agent_id}")
    print("\n🎵 Features:")
    print("   - Natural conversation flow")
    print("   - Deezer music discovery")
    print("   - Song preview playback (fresh URLs)")
    print("   - Related artist suggestions")


if __name__ == "__main__":
    main()
