"""
Mood Enrichment Service

Background worker that enriches user moods with similar artists and genres
using LLM to ensure catalog searches have diverse sources.

This solves the problem where catalog searches only return tracks from
the user's 2-3 favorite artists, causing repetitive selections.
"""
import asyncio
import json
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_db_session
from backend_v2.models.mood import Mood
from backend_v2.models.user_profile import UserProfile
from backend_v2.integrations.openrouter import get_openrouter_client
from backend_v2.orchestration.events import get_event_emitter
from backend_v2.schemas.status_events import StatusCategory, StatusStep

logger = logging.getLogger("ai-dj.mood-enrichment")


async def enrich_mood_with_llm(
    db: AsyncSession,
    mood: Mood,
    user_profile: Optional[UserProfile] = None,
    use_tools: bool = True,
) -> bool:
    """
    Use LLM to generate similar artists and genres for a mood.
    
    Args:
        db: Database session
        mood: Mood to enrich
        user_profile: Optional user profile for context (deprecated, use tools instead)
        use_tools: Whether to use database tools (default True)
        
    Returns:
        True if enrichment was successful
    """
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter not enabled, skipping mood enrichment")
        return False
    
    # Build context from mood and user profile using tools
    favorite_artists = []
    favorite_genres = []
    
    # Variables to hold data (from tools or direct access)
    mood_name = mood.name
    energy_target = mood.energy_target or 0.5
    valence_target = mood.valence_target or 0.5
    danceability_target = mood.danceability_target or 0.5
    existing_genres = []
    
    if use_tools:
        # Use tools to get user profile and mood details
        from backend_v2.integrations.db_tools import execute_tool
        
        try:
            # Get user profile via tool
            user_profile_data = await execute_tool(
                "get_user_profile",
                {"user_id": mood.user_id},
                db
            )
            
            if user_profile_data:
                favorite_artists = user_profile_data.get("favorite_artists", [])
                favorite_genres = user_profile_data.get("favorite_genres", [])
                logger.info(f"🔧 Using TOOL data for user profile: {len(favorite_artists)} artists, {len(favorite_genres)} genres")
            else:
                logger.warning("Tool returned no user_profile_data")
            
            # Get mood details via tool
            mood_details = await execute_tool(
                "get_mood_details",
                {"mood_id": mood.id},
                db
            )
            
            if mood_details:
                # USE TOOL RESULTS instead of mood object
                mood_name = mood_details.get("name", mood.name)
                energy_target = mood_details.get("energy_target", energy_target)
                valence_target = mood_details.get("valence_target", valence_target)
                danceability_target = mood_details.get("danceability_target", danceability_target)
                existing_genres = mood_details.get("genres", [])
                logger.info(f"🔧 Using TOOL data for mood: {mood_name}, energy={energy_target}, valence={valence_target}, genres={len(existing_genres)}")
            else:
                logger.warning("Tool returned no mood_details, falling back to direct access")
                # Fallback to parsing mood object
                if mood.genres_json:
                    try:
                        existing_genres = json.loads(mood.genres_json) or []
                    except:
                        pass
        except Exception as e:
            logger.warning(f"Tool execution failed, falling back to direct access: {e}")
            use_tools = False
    
    if not use_tools:
        # Fallback to direct access (backward compatibility)
        if user_profile:
            # UserProfile uses properties, not _json fields
            favorite_artists = user_profile.favorite_artists or []
            favorite_genres = user_profile.favorite_genres or []
        
        # Parse existing mood data
        if mood.genres_json:
            try:
                existing_genres = json.loads(mood.genres_json) or []
            except:
                pass
    
    # Prompt for similar artist discovery
    system_prompt = """You are a music expert helping build diverse DJ playlists.

Given a mood and user preferences, suggest:
1. 10-15 SIMILAR ARTISTS that match the mood's energy and vibe
2. 5-8 GENRE SEEDS for catalog search (specific subgenres work best)

IMPORTANT:
- Include a MIX of well-known and less-known artists
- Artists should match the mood's energy/valence, not just the user's favorites
- Include artists from different eras but similar vibes
- Genre seeds should be specific (e.g., "indie pop" not just "pop")

Respond with JSON only:
{
    "similar_artists": ["Artist 1", "Artist 2", ...],
    "genre_seeds": ["indie pop", "synth-pop", ...],
    "reasoning": "Brief explanation of choices"
}"""

    user_prompt = f"""Mood: {mood_name}
Energy Target: {energy_target} (0=calm, 1=intense)
Valence Target: {valence_target} (0=sad, 1=happy)
Danceability: {danceability_target}
Current Genres: {', '.join(existing_genres) if existing_genres else 'None set'}

User's Favorite Artists: {', '.join(favorite_artists[:5]) if favorite_artists else 'Not specified'}
User's Favorite Genres: {', '.join(favorite_genres[:5]) if favorite_genres else 'Not specified'}

Generate similar artists and genre seeds that will help create VARIETY in this mood's playlist.
The artists should match the MOOD characteristics, not just be copies of the user's favorites."""

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await client.chat_completion(
            messages=messages,
            temperature=0.8,  # Higher temp for creative suggestions
            json_mode=True,
            use_lite_model=True,  # Use lite model for cost efficiency
            session_id=None,  # Standalone enrichment call
        )
        
        if not result or not result.get('parsed'):
            logger.warning(f"Failed to get LLM response for mood {mood.name}")
            return False
        
        parsed = result['parsed']
        similar_artists = parsed.get('similar_artists', [])
        genre_seeds = parsed.get('genre_seeds', [])
        reasoning = parsed.get('reasoning', '')
        
        if not similar_artists and not genre_seeds:
            logger.warning(f"LLM returned empty results for mood {mood.name}")
            return False
        
        # Update mood with enriched data
        if similar_artists:
            # Merge with existing, avoiding duplicates
            existing_artists = []
            if mood.example_artists_json:
                try:
                    existing_artists = json.loads(mood.example_artists_json) or []
                except:
                    pass
            
            # Add new artists, keeping existing ones
            all_artists = existing_artists + [a for a in similar_artists if a not in existing_artists]
            mood.example_artists_json = json.dumps(all_artists[:20])  # Cap at 20
        
        if genre_seeds:
            # Merge with existing
            existing_seeds = []
            if mood.genre_seeds_json:
                try:
                    existing_seeds = json.loads(mood.genre_seeds_json) or []
                except:
                    pass
            
            all_seeds = existing_seeds + [g for g in genre_seeds if g not in existing_seeds]
            mood.genre_seeds_json = json.dumps(all_seeds[:10])  # Cap at 10
        
        await db.flush()
        
        logger.info(
            f"✅ Enriched mood '{mood.name}': "
            f"{len(similar_artists)} artists, {len(genre_seeds)} genres"
        )
        logger.debug(f"   Reasoning: {reasoning[:100]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"Error enriching mood {mood.name}: {e}")
        return False


async def enrich_all_user_moods(user_id: str) -> int:
    """
    Enrich all moods for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        Number of moods enriched
    """
    async with get_db_session() as db:
        # Get all moods for user (still need to query directly for iteration)
        moods_result = await db.execute(
            select(Mood).where(Mood.user_id == user_id)
        )
        moods = moods_result.scalars().all()
        
        if not moods:
            logger.info(f"No moods found for user {user_id}")
            return 0
        
        enriched_count = 0
        for mood in moods:
            # Skip if already enriched with enough artists
            if mood.example_artists_json:
                try:
                    existing = json.loads(mood.example_artists_json) or []
                    if len(existing) >= 10:
                        logger.debug(f"Mood '{mood.name}' already enriched, skipping")
                        continue
                except:
                    pass
            
            # Use tools=True to use database tools instead of direct queries
            success = await enrich_mood_with_llm(db, mood, user_profile=None, use_tools=True)
            if success:
                enriched_count += 1
            
            # Small delay between LLM calls
            await asyncio.sleep(0.5)
        
        await db.commit()
        return enriched_count


async def run_mood_enrichment_worker():
    """
    Background worker that enriches moods for all users.
    
    Runs on startup and can be triggered periodically.
    """
    logger.info("🎨 Starting mood enrichment worker...")
    
    try:
        async with get_db_session() as db:
            # Find all users with moods that need enrichment
            result = await db.execute(
                select(Mood.user_id).distinct()
            )
            user_ids = [row[0] for row in result.fetchall()]
            
            if not user_ids:
                logger.info("No users with moods found")
                return
            
            logger.info(f"Found {len(user_ids)} users with moods")
            
            total_enriched = 0
            for user_id in user_ids:
                count = await enrich_all_user_moods(user_id)
                total_enriched += count
                
                # Delay between users
                await asyncio.sleep(1.0)
            
            logger.info(f"✅ Mood enrichment complete: {total_enriched} moods enriched")
            
    except Exception as e:
        logger.error(f"Mood enrichment worker error: {e}")
        import traceback
        traceback.print_exc()

# =============================================================================
# EVENT-SPECIFIC TRAINING FUNCTIONS
# =============================================================================

async def train_from_like(
    mood_id: str,
    track_artist: str,
    track_title: str,
) -> bool:
    """
    Train mood from a LIKE event using agentic tool calling.
    
    The agentic trainer dynamically decides which tools to use and
    finds similar artists based on rich context.
    """
    logger.info(f"🎓 Training from LIKE (agentic): {track_artist} - {track_title}")
    
    from backend_v2.orchestration.agentic_trainer import train_with_tools, apply_training_decision_with_metrics
    from backend_v2.integrations.openrouter import get_openrouter_client
    
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter not enabled, skipping training")
        return False
    
    async with get_db_session() as db:
        mood_result = await db.execute(
            select(Mood).where(Mood.id == mood_id)
        )
        mood = mood_result.scalar_one_or_none()
        if not mood:
            logger.warning(f"Mood {mood_id} not found")
            return False
        
        user_id = mood.user_id
        
        # Use agentic trainer with dynamic tool calling
        try:
            result = await train_with_tools(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                feedback_type="like",
                track_artist=track_artist,
                track_title=track_title,
                max_iterations=5,
            )
            
            if not result.get("success"):
                logger.warning(f"Agentic training failed: {result.get('error')}")
                return False
            
            # Apply decision and track metrics
            decision = result.get("decision", {})
            await apply_training_decision_with_metrics(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                decision=decision,
                feedback_type="like",
                track_artist=track_artist,
                track_title=track_title,
                tool_calls_made=result.get("tool_calls", 0),
                llm_tokens=0,  # TODO: Extract from result
            )
            
            logger.info(f"🎓 Agentic training from LIKE complete: {result.get('tool_calls')} tools used")
            
            # Emit status event
            from backend_v2.orchestration.events import get_event_emitter
            from backend_v2.schemas.status_events import StatusCategory, StatusStep
            emitter = get_event_emitter()
            await emitter.emit_status(
                user_id=user_id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message=f"I learned from your like! {decision.get('reasoning', '')}",
                payload={
                    "type": "training_update",
                    "source": "like_agentic",
                    "track": f"{track_artist} - {track_title}",
                    "artists_added": decision.get("artists_to_add", []),
                    "reasoning": decision.get("reasoning", ""),
                    "mood_name": mood.name,
                    "tool_calls": result.get("tool_calls", 0),
                }
            )
            
            return True
        except Exception as e:
            logger.error(f"Agentic training error: {e}", exc_info=True)
            return False


# Legacy implementation kept for reference/fallback
async def _train_from_like_legacy(
    mood_id: str,
    track_artist: str,
    track_title: str,
) -> bool:
    """
    LEGACY: Old train_from_like implementation.
    Kept for reference but not actively used.
    """
    logger.info(f"🎓 Training from LIKE (legacy): {track_artist} - {track_title}")
    
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter not enabled, skipping training")
        return False
    
    async with get_db_session() as db:
        mood_result = await db.execute(
            select(Mood).where(Mood.id == mood_id)
        )
        mood = mood_result.scalar_one_or_none()
        if not mood:
            logger.warning(f"Mood {mood_id} not found")
            return False
        
        existing_artists = []
        if mood.example_artists_json:
            try:
                existing_artists = json.loads(mood.example_artists_json) or []
            except:
                pass
        
        logger.debug(f"   Mood: {mood.name}, Energy: {mood.energy_target}, Valence: {mood.valence_target}")
        logger.debug(f"   Existing artists: {len(existing_artists)}")
        
        # Use database tools to get richer context
        context_info = {}
        try:
            from backend_v2.integrations.db_tools import execute_tool
            
            # Get user's other liked tracks for context
            feedback = await execute_tool(
                "get_user_feedback",
                {"user_id": mood.user_id, "feedback_type": "like", "limit": 10},
                db,
                user_id=mood.user_id,
                mood_id=mood_id,
                agent_name="train_from_like_legacy"
            )
            if feedback:
                liked_artists = [f.get("track_artist", "") for f in feedback if f.get("track_artist")]
                context_info["liked_artists"] = list(set(liked_artists))[:5]
                logger.debug(f"   User has liked {len(liked_artists)} tracks from {len(context_info['liked_artists'])} artists")
            
            # Check if this artist is already in mood
            artist_in_mood = track_artist in existing_artists
            context_info["artist_in_mood"] = artist_in_mood
            logger.debug(f"   Artist {track_artist} already in mood: {artist_in_mood}")
        except Exception as e:
            logger.warning(f"Failed to gather context via tools: {e}")
            # Continue without tool context
        
        system_prompt = """You are a music discovery expert. A user LIKED a track.

Your job: Analyze the track and provide comprehensive recommendations.

1. Find 3-5 similar artists that the user would also enjoy
2. Identify the primary genres of this track (1-3 genres)
3. Suggest any user preference updates based on this like

Focus on:
- Same energy/vibe as the liked track
- Similar genre but not identical
- Mix of well-known and hidden gems
- Artists that complement, not just copy
- Consider the user's existing preferences when suggesting

Respond with JSON:
{
    "add_artists": ["Artist 1", "Artist 2", "Artist 3"],
    "genres": ["genre1", "genre2"],
    "user_preferences": {
        "energy_preference": "high_energy" | "low_energy" | "mixed" | null,
        "tempo_preference": "fast" | "slow" | "mixed" | null,
        "era_preference": "new_releases" | "classics" | "mixed" | null
    },
    "reasoning": "Why these artists are similar and why the user would enjoy them"
}"""

        # Build enriched user prompt with context
        context_parts = []
        if context_info.get("liked_artists"):
            context_parts.append(f"User also likes: {', '.join(context_info['liked_artists'][:3])}")
        if context_info.get("artist_in_mood"):
            context_parts.append(f"Artist already in mood (will be prioritized)")
        
        context_str = "\n".join([f"- {part}" for part in context_parts]) if context_parts else "No additional context"
        
        user_prompt = f"""The user LOVED this track:
🎵 {track_artist} - {track_title}

Mood: {mood.name}
Energy: {mood.energy_target}, Valence: {mood.valence_target}

Current mood artists: {', '.join(existing_artists[:5]) if existing_artists else 'None'}

CONTEXT:
{context_str}

What other artists would this user enjoy? Find artists with similar vibes to {track_artist}."""

        try:
            result = await client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.8,
                json_mode=True,
                use_lite_model=True,
                session_id=None,  # Standalone enrichment call
                db=db,
                user_id=mood.user_id,
                mood_id=mood_id,
                agent_name="train_from_like",
            )
            
            if not result or not result.get('parsed'):
                logger.warning("Failed to get LLM response for like training")
                return False
            
            parsed = result['parsed']
            add_artists = parsed.get('add_artists', [])
            genres = parsed.get('genres', [])
            user_prefs = parsed.get('user_preferences', {})
            reasoning = parsed.get('reasoning', '')
            
            # Validate response structure
            if not isinstance(add_artists, list):
                logger.warning(f"Invalid add_artists format: {add_artists}, expected list")
                add_artists = []
            if not isinstance(genres, list):
                logger.warning(f"Invalid genres format: {genres}, expected list")
                genres = []
            
            if not add_artists:
                logger.warning("No artists returned from LLM")
                return False
            
            logger.debug(f"   LLM response: +{len(add_artists)} artists, +{len(genres)} genres, reasoning={reasoning[:50]}...")
            
            # Update Mood: Add artists
            if track_artist not in existing_artists:
                existing_artists.insert(0, track_artist)
            for artist in reversed(add_artists):
                if artist and artist not in existing_artists:
                    existing_artists.insert(0, artist)
            
            mood.example_artists_json = json.dumps(existing_artists[:25])
            
            # Update Mood: Add genres
            if genres:
                existing_genres = []
                if mood.genres_json:
                    try:
                        existing_genres = json.loads(mood.genres_json) or []
                    except:
                        pass
                
                for genre in genres:
                    if genre and genre.lower() not in [g.lower() for g in existing_genres]:
                        existing_genres.append(genre)
                
                mood.genres_json = json.dumps(existing_genres[:15])
                
                # Also update genre_seeds_json
                existing_seeds = []
                if mood.genre_seeds_json:
                    try:
                        existing_seeds = json.loads(mood.genre_seeds_json) or []
                    except:
                        pass
                
                for genre in genres:
                    if genre and genre.lower() not in [g.lower() for g in existing_seeds]:
                        existing_seeds.insert(0, genre)  # Add at beginning for priority
                
                mood.genre_seeds_json = json.dumps(existing_seeds[:10])
            
            # Update UserProfile: Add favorite song, artist, genres
            from backend_v2.models.user_profile import UserProfile
            user_profile_result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == mood.user_id)
            )
            user_profile = user_profile_result.scalar_one_or_none()
            
            if user_profile:
                # Add favorite song
                favorite_songs = []
                if user_profile.favorite_songs:
                    try:
                        favorite_songs = json.loads(user_profile.favorite_songs) or []
                    except:
                        pass
                
                song_entry = f"{track_title} by {track_artist}"
                if song_entry not in favorite_songs:
                    favorite_songs.insert(0, song_entry)
                    favorite_songs = favorite_songs[:50]  # Cap at 50
                    user_profile.favorite_songs = json.dumps(favorite_songs)
                
                # Add favorite artist
                favorite_artists = []
                if user_profile.favorite_artists:
                    try:
                        favorite_artists = json.loads(user_profile.favorite_artists) or []
                    except:
                        pass
                
                if track_artist not in favorite_artists:
                    favorite_artists.insert(0, track_artist)
                    favorite_artists = favorite_artists[:30]  # Cap at 30
                    user_profile.favorite_artists = json.dumps(favorite_artists)
                
                # Add genres
                if genres:
                    favorite_genres = []
                    if user_profile.favorite_genres:
                        try:
                            favorite_genres = json.loads(user_profile.favorite_genres) or []
                        except:
                            pass
                    
                    for genre in genres:
                        if genre and genre.lower() not in [g.lower() for g in favorite_genres]:
                            favorite_genres.append(genre)
                    
                    user_profile.favorite_genres = json.dumps(favorite_genres[:20])
                
                # Update preferences if provided
                if user_prefs.get("energy_preference"):
                    user_profile.energy_preference = user_prefs["energy_preference"]
                if user_prefs.get("tempo_preference"):
                    user_profile.tempo_preference = user_prefs["tempo_preference"]
                if user_prefs.get("era_preference"):
                    user_profile.era_preference = user_prefs["era_preference"]
            
            # Update MoodProfile with insights for song selection
            # Note: Weight updates are handled by training.py's update_mood_profile_weights()
            # which uses actual song features for more accurate adjustments
            from backend_v2.models.mood import MoodProfile
            profile_result = await db.execute(
                select(MoodProfile).where(MoodProfile.mood_id == mood_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile and reasoning:
                # Append new insight, keep recent ones only
                existing_summary = profile.summary_text or ""
                new_insight = f"• Liked {track_artist} - {track_title}: {reasoning}"
                # Keep last 5 insights
                lines = [l for l in existing_summary.split("\n") if l.strip()][-4:]
                lines.append(new_insight)
                profile.summary_text = "\n".join(lines)
            
            await db.flush()
            await db.commit()
            
            # Invalidate PreferenceBundle cache so new artists are used immediately
            from backend_v2.services.preference_bundle import get_bundle_cache
            cache = get_bundle_cache()
            cache.invalidate(mood.user_id)
            logger.debug(f"Invalidated PreferenceBundle cache for user {mood.user_id}")
            
            logger.info(f"🎓 Trained from LIKE: +{len(add_artists)} similar artists, reasoning={reasoning[:50]}...")
            
            # Emit persistent training event (saved to history)
            emitter = get_event_emitter()
            await emitter.emit_status(
                user_id=mood.user_id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message=f"I learned from your like! Added {len(add_artists)} similar artists and {len(genres)} genres to your {mood.name} vibe.",
                payload={
                    "type": "training_update",
                    "source": "like",
                    "track": f"{track_artist} - {track_title}",
                    "added_artists": add_artists,
                    "added_genres": genres,
                    "added_song": track_title,
                    "reasoning": reasoning,
                    "mood_name": mood.name
                }
            )
            
            return True
                    
        except Exception as e:
            logger.error(f"Train from like error: {e}", exc_info=True)
        
        return False


async def train_from_dislike(
    mood_id: str,
    track_artist: str,
    track_title: str,
) -> bool:
    """
    Train mood from a DISLIKE event using agentic tool calling.
    
    The agentic trainer identifies patterns and removes/demotes disliked content.
    """
    logger.info(f"🎓 Training from DISLIKE (agentic): {track_artist} - {track_title}")
    
    from backend_v2.orchestration.agentic_trainer import train_with_tools, apply_training_decision_with_metrics
    from backend_v2.integrations.openrouter import get_openrouter_client
    
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter not enabled, skipping training")
        return False
    
    async with get_db_session() as db:
        mood_result = await db.execute(
            select(Mood).where(Mood.id == mood_id)
        )
        mood = mood_result.scalar_one_or_none()
        if not mood:
            logger.warning(f"Mood {mood_id} not found")
            return False
        
        user_id = mood.user_id
        
        # Use agentic trainer with dynamic tool calling
        try:
            result = await train_with_tools(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                feedback_type="dislike",
                track_artist=track_artist,
                track_title=track_title,
                max_iterations=5,
            )
            
            if not result.get("success"):
                logger.warning(f"Agentic training failed: {result.get('error')}")
                return False
            
            # Apply decision and track metrics
            decision = result.get("decision", {})
            await apply_training_decision_with_metrics(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                decision=decision,
                feedback_type="dislike",
                track_artist=track_artist,
                track_title=track_title,
                tool_calls_made=result.get("tool_calls", 0),
                llm_tokens=0,
            )
            
            logger.info(f"🎓 Agentic training from DISLIKE complete")
            
            # Emit status event
            # Emit status event
            from backend_v2.orchestration.events import get_event_emitter
            from backend_v2.schemas.status_events import StatusCategory, StatusStep
            emitter = get_event_emitter()
            await emitter.emit_status(
                user_id=user_id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message=f"I learned from your dislike! {decision.get('reasoning', '')}",
                payload={
                    "type": "training_update",
                    "source": "dislike_agentic",
                    "track": f"{track_artist} - {track_title}",
                    "reasoning": decision.get("reasoning", ""),
                    "mood_name": mood.name,
                }
            )
            
            return True
        except Exception as e:
            logger.error(f"Agentic training error: {e}", exc_info=True)
            return False


# Keep the rest of the legacy implementation below
async def _train_from_dislike_legacy_placeholder():
    """Legacy implementation - kept below for reference."""
    pass

# Temporary marker - the legacy implementation continues below
async def _legacy_train_from_dislike_impl_start():
    """Legacy implementation - kept below for reference."""
    pass


async def train_from_skip(
    mood_id: str,
    track_artist: str,
    track_title: str,
) -> bool:
    """
    Train mood from a SKIP event using agentic tool calling.
    
    The agentic trainer investigates why the skip occurred (overplayed, wrong timing, etc).
    """
    logger.info(f"🎓 Training from SKIP (agentic): {track_artist} - {track_title}")
    
    from backend_v2.orchestration.agentic_trainer import train_with_tools, apply_training_decision_with_metrics
    from backend_v2.integrations.openrouter import get_openrouter_client
    
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter not enabled, skipping training")
        return False
    
    async with get_db_session() as db:
        mood_result = await db.execute(
            select(Mood).where(Mood.id == mood_id)
        )
        mood = mood_result.scalar_one_or_none()
        if not mood:
            logger.warning(f"Mood {mood_id} not found")
            return False
        
        user_id = mood.user_id
        
        # Use agentic trainer with dynamic tool calling
        try:
            result = await train_with_tools(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                feedback_type="skip",
                track_artist=track_artist,
                track_title=track_title,
                max_iterations=5,
            )
            
            if not result.get("success"):
                logger.warning(f"Agentic training failed: {result.get('error')}")
                return False
            
            # Apply decision and track metrics
            decision = result.get("decision", {})
            await apply_training_decision_with_metrics(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                decision=decision,
                feedback_type="skip",
                track_artist=track_artist,
                track_title=track_title,
                tool_calls_made=result.get("tool_calls", 0),
                llm_tokens=0,
            )
            
            logger.info(f"🎓 Agentic training from SKIP complete")
            
            # Emit status event
            # Emit status event
            from backend_v2.orchestration.events import get_event_emitter
            from backend_v2.schemas.status_events import StatusCategory, StatusStep
            emitter = get_event_emitter()
            await emitter.emit_status(
                user_id=user_id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message=f"Noted your skip - {decision.get('reasoning', '')}",
                payload={
                    "type": "training_update",
                    "source": "skip_agentic",
                    "track": f"{track_artist} - {track_title}",
                    "reasoning": decision.get("reasoning", ""),
                    "mood_name": mood.name,
                }
            )
            
            return True
        except Exception as e:
            logger.error(f"Agentic training error: {e}", exc_info=True)
            return False


# Keep the rest of the legacy implementation below
async def _train_from_skip_legacy_placeholder():
    """Legacy implementation - kept below for reference."""
    pass

# Temporary marker - the legacy implementation continues below
async def _legacy_train_from_skip_impl_start():
    pass

# Legacy implementation marker -  the original train_from_skip code continues here with original mood lookup:
async def _legacy_continue():
    """The legacy implementation code block continues from here..."""
    mood = None  # Original mood lookup happened above
    if mood:
        
        existing_artists = []
        if mood.example_artists_json:
            try:
                existing_artists = json.loads(mood.example_artists_json) or []
            except:
                pass
        
        logger.debug(f"   Mood: {mood.name}, Energy: {mood.energy_target}, Valence: {mood.valence_target}")
        logger.debug(f"   Existing artists: {len(existing_artists)}")
        
        # Use database tools to get richer context
        context_info = {}
        try:
            from backend_v2.integrations.db_tools import execute_tool
            
            # Check recent plays of this artist
            play_history = await execute_tool(
                "get_play_history",
                {"user_id": mood.user_id, "artist_name": track_artist, "limit": 5},
                db,
                user_id=mood.user_id,
                mood_id=mood_id,
                agent_name="train_from_skip"
            )
            if play_history:
                context_info["recent_plays"] = len(play_history)
                logger.debug(f"   Artist {track_artist} played {len(play_history)} times recently")
            
            # Check artist play count
            play_count = await execute_tool(
                "get_artist_play_count",
                {"user_id": mood.user_id, "artist_name": track_artist, "last_n_tracks": 20},
                db,
                user_id=mood.user_id,
                agent_name="train_from_skip"
            )
            if play_count:
                context_info["play_count"] = play_count.get("count", 0)
                logger.debug(f"   Artist {track_artist} appears {play_count.get('count', 0)} times in last 20 tracks")
            
            # Get related feedback
            feedback = await execute_tool(
                "get_user_feedback",
                {"user_id": mood.user_id, "limit": 10},
                db,
                user_id=mood.user_id,
                agent_name="train_from_skip"
            )
            if feedback:
                related_feedback = [f for f in feedback if track_artist.lower() in f.get("track_artist", "").lower()]
                context_info["related_feedback"] = len(related_feedback)
                logger.debug(f"   Found {len(related_feedback)} related feedback entries")
        except Exception as e:
            logger.warning(f"Failed to gather context via tools: {e}")
            # Continue without tool context
        
        system_prompt = """You are a music analysis expert. A user SKIPPED a track.

Skips can mean many things:
- Not in the mood right now (soft signal - don't overreact)
- Not a good fit for this mood (medium signal - find alternatives)
- Heard it too recently (timing issue - check play history)
- Wrong energy/vibe (strong signal - demote and find better match)

Your job: Analyze WHY they skipped and suggest appropriate actions.

CRITICAL: Only demote if there's a clear pattern (e.g., multiple skips of this artist, or clear mismatch with mood).

Respond with JSON:
{
    "should_demote": true/false,
    "demote_reason": "Why demote (if true)",
    "alternatives": ["Alt 1", "Alt 2", "Alt 3"],
    "genres": ["genre1", "genre2"],
    "insights": "What this skip tells us about preferences"
}"""

        # Build enriched user prompt with context
        context_parts = []
        if context_info.get("recent_plays"):
            context_parts.append(f"Artist played {context_info['recent_plays']} times recently")
        if context_info.get("play_count"):
            context_parts.append(f"Artist appears {context_info['play_count']} times in last 20 tracks")
        if context_info.get("related_feedback"):
            context_parts.append(f"Found {context_info['related_feedback']} related feedback entries")
        
        context_str = "\n".join([f"- {part}" for part in context_parts]) if context_parts else "No recent context available"
        
        user_prompt = f"""The user SKIPPED this track:
⏭️ {track_artist} - {track_title}

Mood: {mood.name}
Energy: {mood.energy_target}, Valence: {mood.valence_target}

Current mood artists: {', '.join(existing_artists[:5]) if existing_artists else 'None'}

CONTEXT:
{context_str}

What does this skip tell us? Should we adjust the mood's artist list?"""

        try:
            result = await client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.6,
                json_mode=True,
                use_lite_model=True,
                session_id=None,  # Standalone enrichment call
                db=db,
                user_id=mood.user_id,
                mood_id=mood_id,
                agent_name="train_from_skip",
            )
            
            if not result or not result.get('parsed'):
                logger.warning("Failed to get LLM response for skip training")
                return False
            
            parsed = result['parsed']
            
            # Validate response structure
            should_demote = parsed.get('should_demote', False)
            alternatives = parsed.get('alternatives', [])
            genres = parsed.get('genres', [])
            insights = parsed.get('insights', '')
            demote_reason = parsed.get('demote_reason', '')
            
            if not isinstance(alternatives, list):
                logger.warning(f"Invalid alternatives format: {alternatives}, expected list")
                alternatives = []
            if not isinstance(genres, list):
                genres = []
            
            logger.debug(f"   LLM response: demote={should_demote}, alternatives={len(alternatives)}, genres={len(genres)}, insights={insights[:50]}...")
            
            # Soft demote: move to end of list rather than remove
            if should_demote and track_artist in existing_artists:
                existing_artists.remove(track_artist)
                existing_artists.append(track_artist)  # Move to end
                logger.debug(f"   Demoted {track_artist} to end of list")
            
            # Add alternatives near beginning
            added_count = 0
            for artist in reversed(alternatives):
                if artist and artist not in existing_artists:
                    existing_artists.insert(2, artist)  # After top 2
                    added_count += 1
            
            mood.example_artists_json = json.dumps(existing_artists[:25])
            
            # Update Mood: Add genres if provided
            if genres:
                existing_genres = []
                if mood.genres_json:
                    try:
                        existing_genres = json.loads(mood.genres_json) or []
                    except:
                        pass
                
                for genre in genres:
                    if genre and genre.lower() not in [g.lower() for g in existing_genres]:
                        existing_genres.append(genre)
                
                mood.genres_json = json.dumps(existing_genres[:15])
            
            # Update MoodProfile with insights for song selection
            from backend_v2.models.mood import MoodProfile
            profile_result = await db.execute(
                select(MoodProfile).where(MoodProfile.mood_id == mood_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile and insights:
                existing_summary = profile.summary_text or ""
                new_insight = f"• Skipped {track_artist} - {track_title}: {insights}"
                lines = [l for l in existing_summary.split("\n") if l.strip()][-4:]
                lines.append(new_insight)
                profile.summary_text = "\n".join(lines)
            
            await db.flush()
            await db.commit()
            
            # Invalidate PreferenceBundle cache so new artists are used immediately
            from backend_v2.services.preference_bundle import get_bundle_cache
            cache = get_bundle_cache()
            cache.invalidate(mood.user_id)
            logger.debug(f"Invalidated PreferenceBundle cache for user {mood.user_id}")
            
            logger.info(f"🎓 Trained from SKIP: demote={should_demote}, +{added_count} alternatives, insights={insights[:50]}...")
            
            # Emit persistent training event (saved to history) - using emitter pattern like like/dislike
            emitter = get_event_emitter()
            await emitter.emit_status(
                user_id=mood.user_id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message=f"I noted your skip. Adjusting {mood.name} to play less {track_artist} and try alternatives like {', '.join(alternatives[:2]) if alternatives else 'similar artists'}.",
                payload={
                    "type": "training_update",
                    "source": "skip",  # Frontend expects this
                    "track": f"{track_artist} - {track_title}",
                    "added_artists": alternatives,
                    "added_genres": genres,
                    "demoted": should_demote,
                    "demote_reason": demote_reason if should_demote else None,
                    "insights": insights,
                    "mood_name": mood.name
                }
            )
            
            return True
                    
        except Exception as e:
            logger.error(f"Train from skip error: {e}", exc_info=True)
        
        return False


# Singleton for tracking if worker has run
_enrichment_done = False


async def train_mood_from_session(
    session_id: str,
    user_id: str,
    mood_id: str,
) -> bool:
    """
    Train a mood based on session feedback and plays.
    
    Analyzes:
    - Liked tracks: Artists/genres to add more of
    - Disliked tracks: Artists/genres to avoid
    - Skipped tracks: Potential mismatches
    - Completed plays: Good fits to learn from
    
    Updates the mood's example_artists and genre_seeds based on learnings.
    
    Args:
        session_id: Session to analyze
        user_id: User ID
        mood_id: Mood to train
        
    Returns:
        True if training was successful
    """
    from backend_v2.models.feedback import FeedbackEvent
    from backend_v2.models.existing import PlayHistory, Song
    
    logger.info(f"🎓 Training mood from session {session_id[:8]}...")
    
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter not enabled, skipping mood training")
        return False
    
    async with get_db_session() as db:
        # Get the mood
        mood_result = await db.execute(
            select(Mood).where(Mood.id == mood_id)
        )
        mood = mood_result.scalar_one_or_none()
        if not mood:
            logger.warning(f"Mood {mood_id} not found")
            return False
        
        # Get recent feedback for this mood (FeedbackEvent doesn't have session_id)
        feedback_result = await db.execute(
            select(FeedbackEvent).where(
                FeedbackEvent.mood_id == mood_id,
                FeedbackEvent.user_id == user_id
            ).order_by(FeedbackEvent.created_at.desc()).limit(20)
        )
        feedback_events = feedback_result.scalars().all()
        
        # Get play history from this session
        plays_result = await db.execute(
            select(PlayHistory, Song).join(
                Song, PlayHistory.song_uuid == Song.uuid
            ).where(
                PlayHistory.session_id == session_id,
                PlayHistory.user_id == user_id
            )
        )
        plays = plays_result.all()
        
        # Organize feedback
        liked_tracks = []
        disliked_tracks = []
        
        for event in feedback_events:
            val = str(event.value).lower()
            if val == "like" or val == "1":
                liked_tracks.append(f"{event.track_artist} - {event.track_title}")
            elif val == "dislike" or val == "-1":
                disliked_tracks.append(f"{event.track_artist} - {event.track_title}")
        
        # Organize plays
        completed_tracks = []
        skipped_tracks = []
        
        for play, song in plays:
            track_info = f"{song.artist} - {song.title}"
            if play.skipped:
                skipped_tracks.append(track_info)
            else:
                completed_tracks.append(track_info)
        
        # If no meaningful data, skip training
        if not liked_tracks and not disliked_tracks and len(completed_tracks) < 3:
            logger.info(f"Not enough session data to train mood {mood.name}")
            return False
        
        # Get existing mood artists for context
        existing_artists = []
        if mood.example_artists_json:
            try:
                existing_artists = json.loads(mood.example_artists_json) or []
            except:
                pass
        
        logger.debug(f"   Session data: {len(liked_tracks)} liked, {len(disliked_tracks)} disliked, {len(skipped_tracks)} skipped, {len(completed_tracks)} completed")
        logger.debug(f"   Existing artists: {len(existing_artists)}")
        
        # Use database tools to get richer context
        context_info = {}
        try:
            from backend_v2.integrations.db_tools import execute_tool
            
            # Get user's overall feedback patterns
            feedback_summary = await execute_tool(
                "get_feedback_summary",
                {"user_id": user_id, "mood_id": mood_id},
                db,
                user_id=user_id,
                mood_id=mood_id,
                agent_name="train_mood_from_session"
            )
            if feedback_summary:
                context_info["feedback_summary"] = feedback_summary
                logger.debug(f"   Feedback summary: {feedback_summary.get('total_likes', 0)} likes, {feedback_summary.get('total_dislikes', 0)} dislikes")
        except Exception as e:
            logger.warning(f"Failed to gather context via tools: {e}")
            # Continue without tool context
        
        # Build training prompt
        system_prompt = """You are a music AI learning from user listening behavior.

Analyze the session data and provide insights to improve future recommendations.

Based on the feedback:
1. Identify 3-5 NEW similar artists to ADD (based on liked tracks - find artists similar to what they enjoyed)
2. Identify any artists to DEMOTE (based on dislikes/skips - be conservative, only demote if clear pattern)
3. Suggest any genre adjustments (optional, only if clear patterns emerge)

CRITICAL RULES:
- Only add artists that match the mood's energy/valence
- Only demote if there's a clear pattern (multiple dislikes/skips of same artist)
- Consider the user's overall preferences when making suggestions
- Focus on quality over quantity - better to add 3 great matches than 10 mediocre ones

Respond with JSON:
{
    "add_artists": ["Artist 1", "Artist 2"],
    "demote_artists": ["Artist X"],
    "genre_adjustments": ["add: bedroom pop", "reduce: hard rock"],
    "insights": "What this session tells us about user preferences"
}"""

        # Build enriched user prompt with context
        context_parts = []
        if context_info.get("feedback_summary"):
            summary = context_info["feedback_summary"]
            if summary.get("total_likes", 0) > 0 or summary.get("total_dislikes", 0) > 0:
                context_parts.append(f"Overall: {summary.get('total_likes', 0)} likes, {summary.get('total_dislikes', 0)} dislikes")
        
        context_str = "\n".join([f"- {part}" for part in context_parts]) if context_parts else "No additional context"
        
        user_prompt = f"""Mood: {mood.name}
Energy: {mood.energy_target}, Valence: {mood.valence_target}

SESSION FEEDBACK:
Liked: {', '.join(liked_tracks) if liked_tracks else 'None'}
Disliked: {', '.join(disliked_tracks) if disliked_tracks else 'None'}
Skipped: {', '.join(skipped_tracks) if skipped_tracks else 'None'}
Completed (no skip): {', '.join(completed_tracks[:10]) if completed_tracks else 'None'}

Current mood artists: {', '.join(existing_artists[:10]) if existing_artists else 'Not set'}

CONTEXT:
{context_str}

What should we learn from this session to improve future recommendations?"""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            result = await client.chat_completion(
                messages=messages,
                temperature=0.5,  # Lower temp for analysis
                json_mode=True,
                use_lite_model=True,
                session_id=None,  # Standalone training call
                db=db,
                user_id=user_id,
                mood_id=mood_id,
                agent_name="train_mood_from_session",
            )
            
            if not result or not result.get('parsed'):
                logger.warning(f"Failed to get training response for mood {mood.name}")
                return False
            
            parsed = result['parsed']
            add_artists = parsed.get('add_artists', [])
            demote_artists = parsed.get('demote_artists', [])
            insights = parsed.get('insights', '')
            genre_adjustments = parsed.get('genre_adjustments', [])
            
            # Validate response structure
            if not isinstance(add_artists, list):
                logger.warning(f"Invalid add_artists format: {add_artists}, expected list")
                add_artists = []
            if not isinstance(demote_artists, list):
                logger.warning(f"Invalid demote_artists format: {demote_artists}, expected list")
                demote_artists = []
            
            logger.debug(f"   LLM response: +{len(add_artists)} artists, -{len(demote_artists)} demoted, insights={insights[:50]}...")
            
            # Update mood artists
            if add_artists or demote_artists:
                # Remove demoted artists
                demote_lower = [a.lower() for a in demote_artists]
                updated_artists = [
                    a for a in existing_artists
                    if a.lower() not in demote_lower
                ]
                
                # Add new artists at the beginning (higher priority)
                added_count = 0
                for artist in reversed(add_artists):
                    if artist and artist not in updated_artists:
                        updated_artists.insert(0, artist)
                        added_count += 1
                
                # Cap at 25 artists
                mood.example_artists_json = json.dumps(updated_artists[:25])
                
                # Update MoodProfile with comprehensive session insights
                from backend_v2.models.mood import MoodProfile
                profile_result = await db.execute(
                    select(MoodProfile).where(MoodProfile.mood_id == mood_id)
                )
                profile = profile_result.scalar_one_or_none()
                if profile and insights:
                    # Create comprehensive session summary
                    summary_parts = []
                    if liked_tracks:
                        summary_parts.append(f"Enjoyed: {', '.join(liked_tracks[:3])}")
                    if disliked_tracks:
                        summary_parts.append(f"Didn't like: {', '.join(disliked_tracks[:3])}")
                    if skipped_tracks:
                        summary_parts.append(f"Skipped: {', '.join(skipped_tracks[:3])}")
                    summary_parts.append(f"Analysis: {insights}")
                    
                    profile.summary_text = "\n".join(summary_parts)
                
                await db.flush()
                await db.commit()
                
                # Invalidate PreferenceBundle cache so new artists are used immediately
                from backend_v2.services.preference_bundle import get_bundle_cache
                cache = get_bundle_cache()
                cache.invalidate(user_id)
                logger.debug(f"Invalidated PreferenceBundle cache for user {user_id}")
                
                logger.info(
                    f"🎓 Trained mood '{mood.name}': "
                    f"+{added_count} artists, -{len(demote_artists)} demoted"
                )
                logger.debug(f"   Insights: {insights[:100]}...")
                
                # Emit persistent training event (saved to history)
                from backend_v2.orchestration.events import get_event_emitter
                from backend_v2.schemas.status_events import StatusCategory, StatusStep
                emitter = get_event_emitter()
                await emitter.emit_status(
                    user_id=user_id,
                    category=StatusCategory.TRAINING,
                    step=StatusStep.TRAINING_COMPLETE,
                    user_message=f"Session review complete! Updated {mood.name} with {added_count} new artists and insights from your listening.",
                    payload={
                        "type": "training_update",
                        "source": "session_review",
                        "session_id": session_id,
                        "added_artists": add_artists,
                        "demoted_artists": demote_artists,
                        "genre_adjustments": genre_adjustments,
                        "insights": insights,
                        "mood_name": mood.name,
                        "liked_count": len(liked_tracks),
                        "disliked_count": len(disliked_tracks),
                        "skipped_count": len(skipped_tracks)
                    }
                )
                
                return True
            
            logger.info(f"No artist changes needed for mood {mood.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error training mood {mood.name}: {e}", exc_info=True)
            return False


async def ensure_moods_enriched():
    """
    Ensure mood enrichment has run at least once during this process.
    Safe to call multiple times.
    """
    global _enrichment_done
    if _enrichment_done:
        return
    
    _enrichment_done = True
    
    # Run in background to not block startup
    asyncio.create_task(run_mood_enrichment_worker())
