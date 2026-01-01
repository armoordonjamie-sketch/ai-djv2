"""DJ Loop for continuous AI DJ orchestration.

Manages the planning loop that continuously generates audio segments.
Each loop iteration:
1. Builds/refreshes PreferenceBundle from database
2. Selects next track using AI + deterministic scoring
3. Plans transition from current track
4. Optionally generates TTS speech
5. Renders audio segment with transitions
6. Queues segment for streaming and emits events

Evidence: Implementing Phase 5 (DJLoop wiring) of implementation_plan.md
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

from backend_v2.orchestration.state import (
    DJState,
    SessionContext,
    create_initial_state,
    add_decision_step,
)
from backend_v2.orchestration.events import get_event_emitter
from backend_v2.schemas.status_events import StatusCategory, StatusStep, Severity
from backend_v2.config import SEGMENT_DIR, SONG_CACHE_DIR
from backend_v2.db.session import get_db_session

logger = logging.getLogger("ai-dj.loop")


class DJLoop:
    """Continuous DJ orchestration loop.
    
    Runs as a background task for each user session.
    Produces audio segments that are fed to the streaming pipeline.
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        mood_id: Optional[str] = None,
        context_name: Optional[str] = None,
        segment_queue: Optional[asyncio.Queue] = None,
        resume_song_uuid: Optional[str] = None,
        resume_position_sec: Optional[float] = None,
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.mood_id = mood_id
        self.context_name = context_name  # Changed from context_id
        
        # Resume state (for continuing playback from saved position)
        self.resume_song_uuid = resume_song_uuid
        self.resume_position_sec = resume_position_sec
        
        # Output queue for rendered segments (allow 2 segments buffered ahead for smooth playback)
        self.segment_queue = segment_queue or asyncio.Queue(maxsize=3)
        
        # State
        self.state: DJState = create_initial_state(
            user_id=user_id,
            session_id=session_id,
            mood_id=mood_id,
            context_id=context_name,
        )
        
        # Control
        self.is_running = False
        self._shutdown = False
        self._task: Optional[asyncio.Task] = None
        
        # Planning state
        self.current_song: Optional[Dict[str, Any]] = None
        self.songs_played: List[str] = []
        self.segments_produced = 0
        self.songs_since_last_speech = 0
        self.banter_history: List[str] = []
        self.failed_song_uuids: List[str] = []
        self.transition_history: List[str] = []
        self.intro_already_used = False  # Track if pre-generated intro has been used
        
    async def start(self):
        """Start the DJ loop."""
        if self.is_running:
            logger.warning(f"DJLoop for user {self.user_id} already running")
            return
            
        self.is_running = True
        self._shutdown = False
        
        logger.info(f"🎧 Starting DJLoop for user {self.user_id}")
        
        # Start background task
        self._task = asyncio.create_task(self._run())
        
    async def stop(self):
        """Stop the DJ loop."""
        logger.info(f"🎧 Stopping DJLoop for user {self.user_id}")
        self._shutdown = True
        self.is_running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
        logger.info(f"🎧 DJLoop stopped for user {self.user_id}")
        
    async def _run(self):
        """Main orchestration loop."""
        logger.info(f"🎧 DJLoop running for user {self.user_id}")
        
        emitter = get_event_emitter()
        
        try:
            # Continuous planning
            while not self._shutdown:
                try:
                    # Check segment queue backpressure
                    # Only 1 segment should be queued at a time (each segment includes transition to next song)
                    queue_size = self.segment_queue.qsize()
                    if queue_size >= 1:
                        # Queue has a segment - wait briefly then check again
                        # Production will be triggered when segment starts playing (queue becomes empty)
                        await asyncio.sleep(0.5)  # Check more frequently for responsive production
                        continue
                    
                    # Queue is empty - produce next segment
                    # If no current song, ensure we start with an initial segment
                    if not self.current_song:
                        await self._produce_initial_segment()
                        if not self.current_song:
                            # Failed (e.g. empty library), wait and retry
                            logger.warning("Initial segment production failed or yielded no song, retrying...")
                            await asyncio.sleep(5)
                            continue
                    else:
                        # Plan and render next segment
                        await self._produce_mix_segment()
                    
                    # After producing, check queue immediately (segment may have started playing)
                    # This ensures we start producing the next segment as soon as current one starts
                    await asyncio.sleep(0.1)  # Minimal delay to allow segment to be consumed
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"DJLoop error for user {self.user_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    await asyncio.sleep(5)
                    
        except asyncio.CancelledError:
            pass
        finally:
            logger.info(f"🎧 DJLoop exited for user {self.user_id}")
    
    async def _build_bundle(self):
        """Build PreferenceBundle from database."""
        from backend_v2.services.preference_bundle import build_preference_bundle
        
        async with get_db_session() as db:
            bundle = await build_preference_bundle(
                db=db,
                user_id=self.user_id,
                session_id=self.session_id,
                mood_id=self.mood_id,
                context_name=self.context_name,
                use_cache=True,
            )
            # CRITICAL: Commit any lazily created defaults (moods/contexts)
            # so that subsequent transactions (like LLM traces) can reference them.
            await db.commit()
            return bundle
    
    async def _update_session_current_track(self, song_info: Dict[str, Any]):
        """Update session database with current track info for resume functionality."""
        from backend_v2.models.existing import Session
        from sqlalchemy import select
        
        try:
            async with get_db_session() as db:
                result = await db.execute(
                    select(Session).where(Session.session_id == self.session_id)
                )
                session = result.scalar_one_or_none()
                
                if session:
                    session.current_song_uuid = song_info.get("uuid")
                    session.current_song_title = song_info.get("title")
                    session.current_song_artist = song_info.get("artist")
                    session.current_song_artwork = song_info.get("artwork_url")
                    await db.commit()
                    logger.debug(
                        f"Updated session current track: {song_info.get('artist')} - {song_info.get('title')}"
                    )
        except Exception as e:
            logger.warning(f"Failed to update session current track: {e}")
            
    async def _produce_initial_segment(self):
        """Produce the first segment (intro with TTS), or resume from saved position."""
        
        # Check if we're resuming from a saved position
        if self.resume_song_uuid and self.resume_position_sec and self.resume_position_sec > 0:
            logger.info(f"Resuming playback for user {self.user_id} at position {self.resume_position_sec}s")
            
            # Fetch the song from database
            from backend_v2.models.existing import Song
            from sqlalchemy import select
            
            async with get_db_session() as db:
                result = await db.execute(select(Song).where(Song.uuid == self.resume_song_uuid))
                song = result.scalar_one_or_none()
                
                if song and song.local_path and os.path.exists(song.local_path):
                    # Queue the resumed song with start offset
                    segment_meta = {
                        "path": song.local_path,
                        "song_uuid": song.uuid,
                        "title": song.title,
                        "artist": song.artist,
                        "artwork_url": song.artwork_url,
                        "duration": song.duration_sec,
                        "start_offset_sec": self.resume_position_sec,  # FFmpeg will seek to this position
                    }
                    await self.segment_queue.put(segment_meta)
                    self.segments_produced += 1
                    
                    # Set as current song
                    self.current_song = {
                        "uuid": song.uuid,
                        "title": song.title,
                        "artist": song.artist,
                        "artwork_url": song.artwork_url,
                        "local_path": song.local_path,
                        "duration": song.duration_sec,
                    }
                    
                    logger.info(f"Resumed with song: {song.artist} - {song.title} at {self.resume_position_sec}s")
                    return
                else:
                    logger.warning(f"Resume song {self.resume_song_uuid} not found or file missing, starting fresh")
                    # Clear resume flags and continue with fresh start
                    self.resume_song_uuid = None
                    self.resume_position_sec = None
        
        logger.info(f"Producing initial segment for user {self.user_id}")
        
        emitter = get_event_emitter()
        
        # Emit planning status
        await emitter.emit_status(
            user_id=self.user_id,
            category=StatusCategory.GENERATION,
            step=StatusStep.PLANNING,
            user_message="Your AI DJ is planning your first track...",
            session_id=self.session_id,
            debug_message="Building preference bundle and selecting initial song",
        )
        
        try:
            from backend_v2.orchestration.agents import (
                select_track,
                select_track_via_catalog,
                write_intro_speech,
                synthesize_speech,
                persist_segment,
                persist_play_history,
                should_dj_speak,
            )
            from backend_v2.audio.mix import create_intro_mix
            
            # Step 1: Build preference bundle
            bundle = await self._build_bundle()
            
            # Pre-generated Intro Check:
            # Use pre-generated intros whenever they exist to start playback quickly.
            intro_available = (
                bundle.mood and
                bundle.mood.intro_segment_path and
                not self.intro_already_used
            )
            
            if intro_available:
                intro_path = bundle.mood.intro_segment_path
                if os.path.exists(intro_path):
                    logger.info(f"Using pre-generated intro for mood '{bundle.mood.name}': {intro_path}")
                    self.intro_already_used = True  # Mark as used to prevent reuse
                    
                    from backend_v2.audio.mix import get_duration
                    from backend_v2.models.existing import Song
                    from sqlalchemy import select
                    from backend_v2.orchestration.agents import persist_segment, persist_play_history
                    
                    # Get duration
                    duration = get_duration(intro_path)
                    
                    # Fetch song details
                    song_uuid = bundle.mood.intro_song_uuid
                    song_title = "Unknown"
                    song_artist = "Unknown"
                    song_artwork = None
                    song_local_path = None
                    
                    if song_uuid:
                        async with get_db_session() as db:
                            res = await db.execute(select(Song).where(Song.uuid == song_uuid))
                            song = res.scalar_one_or_none()
                            if song:
                                song_title = song.title
                                song_artist = song.artist
                                song_artwork = song.artwork_url
                                song_local_path = song.local_path

                    now_playing_offset_sec = 0.0
                    meta_path = f"{intro_path}.json"
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, "r", encoding="utf-8") as f:
                                intro_meta = json.load(f)
                            intro_info = intro_meta.get("intro") or {}
                            song_start_sec = intro_info.get("song_start_sec")
                            if isinstance(song_start_sec, (int, float)) and song_start_sec > 0:
                                now_playing_offset_sec = song_start_sec
                            else:
                                tts_meta = intro_meta.get("tts") or {}
                                tts_duration = tts_meta.get("duration")
                                if isinstance(tts_duration, (int, float)) and tts_duration > 0:
                                    now_playing_offset_sec = 2.5 + max(tts_duration - 1.0, 0.0)
                        except Exception as e:
                            logger.warning(
                                "Failed to read intro metadata for now_playing offset: %s",
                                e,
                            )
                    
                    # Queue intro WITH song metadata so UI can display what's playing
                    segment_meta = {
                        "path": intro_path,
                        "song_uuid": song_uuid,
                        "title": song_title,
                        "artist": song_artist,
                        "artwork_url": song_artwork,
                        "duration": duration,
                        "now_playing_offset_sec": now_playing_offset_sec,
                        "is_intro": True,  # Mark as intro for special handling in mix logic
                    }
                    await self.segment_queue.put(segment_meta)
                    self.segments_produced += 1
                    
                    # Persist intro play history/segment
                    async with get_db_session() as db:
                         await persist_segment(
                             db=db,
                             user_id=self.user_id,
                             mood_id=self.mood_id,
                             session_id=self.session_id,
                             segment_index=self.segments_produced,
                             song_uuid=song_uuid,
                             file_path=intro_path,
                             duration_sec=duration,
                             tts_used=True,
                             banter_text="[Pre-generated Intro]",
                         )
                         await persist_play_history(
                             db=db,
                             user_id=self.user_id,
                             mood_id=self.mood_id,
                             session_id=self.session_id,
                             song_uuid=song_uuid,
                         )
                         await db.commit()

                    # Update tracking - Set current_song with uuid=None for pre-generated intros
                    # This marks the segment as successfully produced without triggering WS re-emit
                    self.current_song = {
                        "uuid": None,  # No UUID = WS handler won't re-emit this
                        "title": song_title,
                        "artist": song_artist,
                        "local_path": song_local_path,
                        "artwork_url": song_artwork,
                        "duration": duration,
                        "is_intro": True,  # Mark as intro for clarity
                    }
                    self.songs_played.append(song_uuid)
                    self.songs_since_last_speech = 0 # It spoke
                    
                    # Don't update session database with pre-generated intro song
                    # (it's from a previous session and doesn't reflect the current session)
                    
                    await emitter.emit_segment_ready(
                        user_id=self.user_id,
                        segment_index=self.segments_produced,
                        duration_sec=duration,
                        song_uuid=song_uuid,
                    )
                    return

            # RESUME PATH: If resuming from a saved position, use the saved song
            selected = None
            is_resume = False
            if self.resume_song_uuid:
                logger.info(f"Resuming from saved song: {self.resume_song_uuid} at position {self.resume_position_sec}s")
                is_resume = True
                
                from backend_v2.models.existing import Song
                from sqlalchemy import select as sql_select
                
                async with get_db_session() as db:
                    result = await db.execute(
                        sql_select(Song).where(Song.uuid == self.resume_song_uuid)
                    )
                    song = result.scalar_one_or_none()
                    
                    if song and song.local_path and os.path.exists(song.local_path):
                        selected = {
                            "uuid": song.uuid,
                            "title": song.title,
                            "artist": song.artist,
                            "local_path": song.local_path,
                            "artwork_url": song.artwork_url,
                            "rationale": "Resuming from saved position",
                            "features": {},  # Could load from DB if needed
                        }
                        logger.info(f"Resume: Found saved song {song.artist} - {song.title}")
                    else:
                        logger.warning(f"Resume: Song {self.resume_song_uuid} not found or missing file, will select new track")
                
                # Clear resume state after using it
                self.resume_song_uuid = None
            
            # NEW TRACK PATH: Select first track (using new catalog-based flow)
            if not selected:
                async with get_db_session() as db:
                    selected = await select_track_via_catalog(
                        db, bundle, self.state, 
                        prev_song=None,
                        history_ids=self.songs_played + self.failed_song_uuids,
                        use_intent_flow=True,  # Enable new catalog-based flow
                        use_tools=True  # Enable tool calling for better context
                    )
                    await db.commit()
            
            if not selected:
                logger.warning("No track selected for initial segment")
                await emitter.emit_to_user(self.user_id, "dj_says", {
                    "script": "Looking for music..."
                })
                return
            
            song_uuid = selected.get("uuid")
            song_path = selected.get("local_path")
            
            if not song_path or not os.path.exists(song_path):
                logger.warning(f"Song file not found: {song_path}")
                self.failed_song_uuids.append(song_uuid)
                return
            
            # Update state
            self.state = add_decision_step(
                self.state,
                agent="InitialSongSelector",
                action=f"Selected {selected.get('artist')} - {selected.get('title')}",
                rationale=selected.get("rationale", "AI selection"),
            )
            
            # Emit track selected status
            await emitter.emit_status(
                user_id=self.user_id,
                category=StatusCategory.GENERATION,
                step=StatusStep.TRACK_SELECTED,
                user_message=f"{'Resuming' if is_resume else 'Playing'}: {selected.get('artist')} - {selected.get('title')}",
                session_id=self.session_id,
                payload={
                    "track_id": song_uuid,
                    "track_title": selected.get("title"),
                    "track_artist": selected.get("artist"),
                },
            )
            
            # Step 3: Generate intro speech (skip when resuming for seamless playback)
            tts_path = None
            if not is_resume and should_dj_speak(bundle, self.songs_since_last_speech, is_intro=True):
                song_info = {
                    "title": selected.get("title"),
                    "artist": selected.get("artist"),
                    "uuid": song_uuid,
                }
                async with get_db_session() as db:
                    script = await write_intro_speech(
                        db, bundle, song_info, self.banter_history
                    )
                    await db.commit()
                
                if script:
                    tts_path = await synthesize_speech(bundle, script)
                    if tts_path:
                        self.banter_history.append(script)
                        self.songs_since_last_speech = 0
                        logger.info(f"🎤 Intro segment: TTS generated, reset songs_since_last_speech to 0")
                        
                        # Emit DJ says event
                        await emitter.emit_dj_says(
                            user_id=self.user_id,
                            script=script,
                        )
            
            # Step 4: Render intro segment
            # Emit mixing status
            await emitter.emit_status(
                user_id=self.user_id,
                category=StatusCategory.GENERATION,
                step=StatusStep.MIXING,
                user_message="Resuming playback..." if is_resume else "Mixing your intro...",
                session_id=self.session_id,
                debug_message="Resuming from saved position" if is_resume else "Rendering intro segment with crossfade and TTS overlay",
            )
            
            # For resume: skip mixing, queue song file directly with position offset
            if is_resume and self.resume_position_sec and self.resume_position_sec > 0:
                logger.info(f"Resume: Queueing {song_path} starting at {self.resume_position_sec}s")
                
                from backend_v2.audio.mix import get_duration
                song_duration = get_duration(song_path)
                resume_pos = min(self.resume_position_sec, song_duration - 10)  # Don't resume too close to end
                
                segment_meta = {
                    "path": song_path,
                    "song_uuid": song_uuid,
                    "title": selected.get("title", "Unknown"),
                    "artist": selected.get("artist", "Unknown"),
                    "artwork_url": selected.get("artwork_url"),
                    "duration": song_duration - resume_pos,
                    "start_offset_sec": resume_pos,  # Tell pipeline where to start
                    "is_resume": True,
                }
                await self.segment_queue.put(segment_meta)
                self.segments_produced += 1
                
                # Update tracking
                self.current_song = selected
                self.songs_played.append(song_uuid)
                self.songs_since_last_speech += 1
                
                await emitter.emit_segment_ready(
                    user_id=self.user_id,
                    segment_index=self.segments_produced,
                    duration_sec=song_duration - resume_pos,
                    song_uuid=song_uuid,
                )
                
                # Clear resume position
                self.resume_position_sec = None
                return
            
            # Run in thread to avoid blocking main loop during rendering
            result = await asyncio.to_thread(
                create_intro_mix,
                song_path=song_path,
                tts_path=tts_path,
                user_id=self.user_id,
            )
            
            if result:
                segment_path = result["output_path"]
                duration = result["metadata"]["render"]["actual_duration"]
                
                # Queue for streaming (pass path + metadata for now_playing)
                segment_meta = {
                    "path": segment_path,
                    "song_uuid": song_uuid,
                    "title": selected.get("title", "Unknown"),
                    "artist": selected.get("artist", "Unknown"),
                    "artwork_url": selected.get("artwork_url"),
                    "duration": duration,
                }
                await self.segment_queue.put(segment_meta)
                self.segments_produced += 1
                
                # Step 5: Persist results
                async with get_db_session() as db:
                    await persist_segment(
                        db=db,
                        user_id=self.user_id,
                        mood_id=self.mood_id,
                        session_id=self.session_id,
                        segment_index=self.segments_produced,
                        song_uuid=song_uuid,
                        file_path=segment_path,
                        duration_sec=duration,
                        tts_used=tts_path is not None,
                        banter_text=self.banter_history[-1] if self.banter_history else None,
                    )
                    
                    await persist_play_history(
                        db=db,
                        user_id=self.user_id,
                        mood_id=self.mood_id,
                        session_id=self.session_id,
                        song_uuid=song_uuid,
                    )
                    await db.commit()
                
                # Update tracking
                self.current_song = selected
                self.songs_played.append(song_uuid)
                # Only increment if TTS was NOT generated (if TTS was generated, it was already reset to 0)
                if not tts_path:
                    self.songs_since_last_speech += 1
                    logger.info(f"🎤 Intro segment: Incremented songs_since_last_speech to {self.songs_since_last_speech}")
                else:
                    logger.info(f"🎤 Intro segment: TTS was generated, songs_since_last_speech remains at {self.songs_since_last_speech}")
                
                # Emit events
                await emitter.emit_segment_ready(
                    user_id=self.user_id,
                    segment_index=self.segments_produced,
                    duration_sec=duration,
                    song_uuid=song_uuid,
                )
                
                # Emit ready status
                await emitter.emit_status(
                    user_id=self.user_id,
                    category=StatusCategory.GENERATION,
                    step=StatusStep.READY,
                    user_message="Ready to play!",
                    session_id=self.session_id,
                    payload={
                        "segment_index": self.segments_produced,
                        "queue_depth": self.segment_queue.qsize(),
                    },
                )
                
                logger.info(f"Initial segment queued: {segment_path}")
            else:
                logger.error(f"Failed to render initial segment for song {song_uuid}")
                self.failed_song_uuids.append(song_uuid)
                self.current_song = None
                    
        except Exception as e:
            logger.error(f"Failed to produce initial segment: {e}")
            import traceback
            traceback.print_exc()
            
    async def _produce_mix_segment(self):
        """Produce a transition segment."""
        logger.info(f"Producing mix segment for user {self.user_id}")
        
        emitter = get_event_emitter()
        
        # Emit planning status
        await emitter.emit_status(
            user_id=self.user_id,
            category=StatusCategory.GENERATION,
            step=StatusStep.PLANNING,
            user_message="Planning your next track...",
            session_id=self.session_id,
            debug_message="Building preference bundle for next song selection",
        )
        
        try:
            from backend_v2.orchestration.agents import (
                select_track,
                select_track_via_catalog,
                plan_transition,
                write_transition_speech,
                synthesize_speech,
                persist_segment,
                persist_play_history,
                should_dj_speak,
            )
            from backend_v2.audio.mix import create_dj_mix, get_duration
            from backend_v2.audio.transition_params import compute_crossfade_duration
            
            # Need a current song to transition from
            if not self.current_song:
                logger.warning("No current song for mix segment")
                await asyncio.sleep(5)
                return
            
            # Special case: If coming from a pre-generated intro, continue with mix (no new TTS)
            # The intro already played TTS, so we just need to mix to the next track
            if self.current_song.get("is_intro"):
                logger.info("Previous segment was pre-generated intro - continuing with mix (no new TTS)")
                self.current_song["is_intro"] = False  # Clear flag, keep song info for mixing
                # Fall through to normal mix logic below
            
            # Step 1: Build preference bundle
            bundle = await self._build_bundle()
            
            # Emit selecting status
            await emitter.emit_status(
                user_id=self.user_id,
                category=StatusCategory.GENERATION,
                step=StatusStep.SELECTING_TRACK,
                user_message="Finding the perfect next song...",
                session_id=self.session_id,
            )
            
            # Step 2: Select next track (using new catalog-based flow)
            async with get_db_session() as db:
                selected = await select_track_via_catalog(
                    db, bundle, self.state, 
                    prev_song=self.current_song,
                    history_ids=self.songs_played + self.failed_song_uuids,
                    use_intent_flow=True,  # Enable new catalog-based flow
                    use_tools=True  # Enable tool calling for better context
                )
                await db.commit()
            
            if not selected:
                logger.warning("No track selected for mix segment")
                await asyncio.sleep(10)
                return
            
            song_uuid = selected.get("uuid")
            
            # Check if this song failed before
            if song_uuid in self.failed_song_uuids:
                logger.warning(f"Skipping previously failed song: {song_uuid}")
                return
            
            song_path = selected.get("local_path")
            
            if not song_path or not os.path.exists(song_path):
                logger.warning(f"Song file not found: {song_path}")
                self.failed_song_uuids.append(song_uuid)
                return
            
            prev_song_path = self.current_song.get("local_path")
            if not prev_song_path or not os.path.exists(prev_song_path):
                logger.warning("Previous song file not found")
                # Can't do a mix without prev song, just play next as intro
                self.current_song = selected
                return
            
            # Update state
            self.state = add_decision_step(
                self.state,
                agent="TrackSelector",
                action=f"Selected {selected.get('artist')} - {selected.get('title')}",
                rationale=selected.get("rationale", "AI selection"),
            )
            
            # Step 3: Plan transition
            async with get_db_session() as db:
                transition = await plan_transition(
                    db,
                    bundle,
                    self.current_song,
                    selected,
                    recent_transition_types=self.transition_history[-3:],
                )
                await db.commit()

            transition_type = transition.get("transition_type")
            if transition_type:
                self.transition_history.append(transition_type)
                if len(self.transition_history) > 10:
                    self.transition_history = self.transition_history[-10:]
            
            # Step 4: Maybe generate speech
            tts_path = None
            logger.info(
                f"🎤 Mix segment: Checking if DJ should speak. "
                f"songs_since_last_speech={self.songs_since_last_speech}, "
                f"personality={bundle.mood.dj_personality}"
            )
            if should_dj_speak(bundle, self.songs_since_last_speech, is_intro=False):
                logger.info(f"🎤 Generating transition TTS (songs_since_last_speech={self.songs_since_last_speech})")
                context = {
                    "prev_song": {
                        "title": self.current_song.get("title"),
                        "artist": self.current_song.get("artist"),
                    },
                    "next_song": {
                        "title": selected.get("title"),
                        "artist": selected.get("artist"),
                    },
                    "transition_type": transition.get("transition_type"),
                    "songs_since_last_speech": self.songs_since_last_speech,
                }
                
                async with get_db_session() as db:
                    script = await write_transition_speech(
                        db, bundle, context, self.banter_history
                    )
                    await db.commit()
                
                if script:
                    tts_path = await synthesize_speech(bundle, script)
                    if tts_path:
                        logger.info(f"✅ Transition TTS generated: {tts_path}")
                        self.banter_history.append(script)
                        self.songs_since_last_speech = 0
                        
                        await emitter.emit_dj_says(
                            user_id=self.user_id,
                            script=script,
                        )
                    else:
                        logger.warning("Transition TTS script generated but synthesis failed")
                else:
                    logger.debug("Transition speech generation returned no script")
            else:
                logger.info(f"🎤 DJ will not speak (songs_since_last_speech={self.songs_since_last_speech} below threshold)")
                
            # Step 5: Render mix segment
            # Emit mixing status
            await emitter.emit_status(
                user_id=self.user_id,
                category=StatusCategory.GENERATION,
                step=StatusStep.MIXING,
                user_message=f"Creating smooth transition to {selected.get('title')}...",
                session_id=self.session_id,
                debug_message=f"Rendering {transition.get('transition_type', 'crossfade')} transition",
            )
            
            # Run in thread to avoid blocking main loop during rendering
            features_a = self.current_song.get("features") or {}
            features_b = selected.get("features") or {}
            bpm_a = features_a.get("tempo")
            bpm_b = features_b.get("tempo")

            # Extract transition plan values (with LLM-provided timing)
            transition_type = transition.get("transition_type", "crossfade")
            
            # NEW: Extract start_position_a_seconds from LLM plan
            transition_start_a = transition.get("start_position_a_seconds")
            if transition_start_a is not None and isinstance(transition_start_a, (int, float)):
                logger.info(f"🎵 Using LLM-specified start_position_a: {transition_start_a:.1f}s")
            else:
                transition_start_a = None  # Let mixer compute it
            
            # Extract start_position_b_seconds
            transition_start_b = transition.get("start_position_b_seconds")
            if not isinstance(transition_start_b, (int, float)) or transition_start_b <= 0:
                transition_start_b = 8.0

            # Extract mix_length_bars
            transition_bars = transition.get("mix_length_bars")
            if isinstance(transition_bars, (int, float)) and int(transition_bars) in (8, 16, 32):
                transition_bars = int(transition_bars)
            else:
                transition_bars = None

            # NEW: Extract transition_duration_seconds from LLM plan
            transition_duration_sec = transition.get("transition_duration_seconds")
            
            if transition_duration_sec is not None and isinstance(transition_duration_sec, (int, float)):
                # Use LLM-provided duration
                logger.info(f"🎵 Using LLM-specified transition_duration: {transition_duration_sec:.1f}s")
            else:
                # Fallback: compute from mix_length_bars or BPM
                duration_bounds = {
                    "quick_cut": (1.0, 2.0),
                    "bass_swap": (4.0, 8.0),
                    "filter_sweep": (5.0, 10.0),
                    "crossfade": (6.0, 12.0),
                    "eq_blend": (6.0, 12.0),
                    "loop_mix": (6.0, 10.0),
                    "drop_mix": (4.0, 8.0),
                    "vinyl_stop": (2.0, 6.0),
                }
                bounds = duration_bounds.get(transition_type, (4.0, 12.0))
                bars_scale = {8: 0.0, 16: 0.5, 32: 1.0}

                if transition_bars in bars_scale:
                    scale = bars_scale[transition_bars]
                    transition_duration_sec = bounds[0] + (bounds[1] - bounds[0]) * scale
                else:
                    effective_bpm_a = bpm_a or 120.0
                    effective_bpm_b = bpm_b or 120.0
                    base_duration = compute_crossfade_duration(
                        effective_bpm_a,
                        effective_bpm_b,
                        10.0,
                    )
                    transition_duration_sec = max(bounds[0], min(base_duration, bounds[1]))

            logger.info(
                "🎵 Transition plan: type=%s bars=%s start_a=%s start_b=%.1fs duration=%.1fs",
                transition_type,
                transition_bars if transition_bars is not None else "N/A",
                f"{transition_start_a:.1f}s" if transition_start_a else "computed",
                transition_start_b,
                transition_duration_sec,
            )

            mix_kwargs = {
                "song1_path": prev_song_path,
                "song2_path": song_path,
                "transition_type": transition_type,
                "tts_path": tts_path,
                "song2_start_sec": transition_start_b,
                "transition_start_a_sec": transition_start_a,  # NEW: Pass to mixer
                "xfade_dur": transition_duration_sec,           # Use LLM or computed value
                "bpm_a": bpm_a,
                "bpm_b": bpm_b,
                "adaptive_crossfade": False,  # Disabled since we have explicit duration
                "user_id": self.user_id,
            }

            result = await asyncio.to_thread(create_dj_mix, **mix_kwargs)
            
            if result:
                segment_path = result["output_path"]
                metadata = result.get("metadata") or {}
                duration = metadata.get("render", {}).get("actual_duration")
                if not isinstance(duration, (int, float)):
                    duration = get_duration(segment_path)

                transition_meta = metadata.get("transition") or {}
                delay_ms = transition_meta.get("peak_ms")
                if delay_ms is None:
                    delay_ms = transition_meta.get("delay_ms")
                now_playing_offset_sec = 0.0
                if isinstance(delay_ms, (int, float)) and delay_ms > 0:
                    now_playing_offset_sec = delay_ms / 1000.0
                
                # Queue for streaming (pass path + metadata for now_playing)
                segment_meta = {
                    "path": segment_path,
                    "song_uuid": song_uuid,
                    "title": selected.get("title", "Unknown"),
                    "artist": selected.get("artist", "Unknown"),
                    "artwork_url": selected.get("artwork_url"),
                    "duration": duration,
                    "now_playing_offset_sec": now_playing_offset_sec,
                }
                await self.segment_queue.put(segment_meta)
                self.segments_produced += 1
                
                # Step 6: Persist results
                async with get_db_session() as db:
                    await persist_segment(
                        db=db,
                        user_id=self.user_id,
                        mood_id=self.mood_id,
                        session_id=self.session_id,
                        segment_index=self.segments_produced,
                        song_uuid=song_uuid,
                        file_path=segment_path,
                        duration_sec=duration,
                        tts_used=tts_path is not None,
                    )
                    
                    await persist_play_history(
                        db=db,
                        user_id=self.user_id,
                        mood_id=self.mood_id,
                        session_id=self.session_id,
                        song_uuid=song_uuid,
                        transition_type=transition.get("transition_type"),
                    )
                    await db.commit()
                
                # Update tracking
                self.current_song = selected
                self.songs_played.append(song_uuid)
                # Only increment if TTS was NOT generated (if TTS was generated, it was already reset to 0)
                if not tts_path:
                    self.songs_since_last_speech += 1
                    logger.info(f"🎤 Mix segment: Incremented songs_since_last_speech to {self.songs_since_last_speech}")
                else:
                    logger.info(f"🎤 Mix segment: TTS was generated, songs_since_last_speech remains at {self.songs_since_last_speech}")
                
                # Emit events
                await emitter.emit_segment_ready(
                    user_id=self.user_id,
                    segment_index=self.segments_produced,
                    duration_sec=duration,
                    song_uuid=song_uuid,
                )
                
                # Emit ready status
                await emitter.emit_status(
                    user_id=self.user_id,
                    category=StatusCategory.GENERATION,
                    step=StatusStep.READY,
                    user_message=f"Next up: {selected.get('artist')} - {selected.get('title')}",
                    session_id=self.session_id,
                    payload={
                        "track_id": song_uuid,
                        "track_title": selected.get("title"),
                        "track_artist": selected.get("artist"),
                        "segment_index": self.segments_produced,
                        "queue_depth": self.segment_queue.qsize(),
                    },
                )
                
                # NOTE: now_playing is emitted by pipeline when segment STARTS playing
                logger.info(f"Mix segment queued: {segment_path}")
            else:
                logger.error(f"Failed to render mix segment for song {song_uuid}")
                self.failed_song_uuids.append(song_uuid)
                    
        except Exception as e:
            logger.error(f"Failed to produce mix segment: {e}")
            import traceback
            traceback.print_exc()
        
    def get_state(self) -> Dict[str, Any]:
        """Get current loop state."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "is_running": self.is_running,
            "segments_produced": self.segments_produced,
            "current_song": self.current_song.get("title") if self.current_song else None,
            "songs_played": len(self.songs_played),
            "songs_since_last_speech": self.songs_since_last_speech,
            "failed_songs": len(self.failed_song_uuids),
            "decision_trace": list(self.state.get("decision_trace", []))[-5:],
        }
