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
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.mood_id = mood_id
        self.context_name = context_name  # Changed from context_id
        
        # Output queue for rendered segments
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
                    # Check segment queue backpressure (1 segment ahead max)
                    if self.segment_queue.qsize() >= 1:
                        logger.debug("Segment queue full, waiting...")
                        await asyncio.sleep(5)
                        continue
                    
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
                    
                    # Small delay between segments
                    await asyncio.sleep(2)
                    
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
            
    async def _produce_initial_segment(self):
        """Produce the first segment (intro with TTS)."""
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
            
            # Pre-generated Intro Check
            if bundle.mood and bundle.mood.intro_segment_path:
                intro_path = bundle.mood.intro_segment_path
                if os.path.exists(intro_path):
                    logger.info(f"Using pre-generated intro: {intro_path}")
                    
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
                    
                    # Queue
                    segment_meta = {
                        "path": intro_path,
                        "song_uuid": song_uuid,
                        "title": song_title,
                        "artist": song_artist,
                        "artwork_url": song_artwork,
                        "duration": duration,
                    }
                    await self.segment_queue.put(segment_meta)
                    self.segments_produced += 1
                    
                    # Persist
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

                    # Update tracking
                    self.current_song = {
                        "uuid": song_uuid,
                        "title": song_title,
                        "artist": song_artist,
                        "local_path": song_local_path,
                        "artwork_url": song_artwork,
                        "duration": duration,
                    }
                    self.songs_played.append(song_uuid)
                    self.songs_since_last_speech = 0 # It spoke
                    
                    await emitter.emit_segment_ready(
                        user_id=self.user_id,
                        segment_index=self.segments_produced,
                        duration_sec=duration,
                        song_uuid=song_uuid,
                    )
                    return

            # Step 2: Select first track (using new catalog-based flow)
            async with get_db_session() as db:
                selected = await select_track_via_catalog(
                    db, bundle, self.state, 
                    prev_song=None,
                    history_ids=self.songs_played + self.failed_song_uuids,
                    use_intent_flow=True  # Enable new catalog-based flow
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
                user_message=f"Playing: {selected.get('artist')} - {selected.get('title')}",
                session_id=self.session_id,
                payload={
                    "track_id": song_uuid,
                    "track_title": selected.get("title"),
                    "track_artist": selected.get("artist"),
                },
            )
            
            # Step 3: Generate intro speech
            tts_path = None
            if should_dj_speak(bundle, self.songs_since_last_speech, is_intro=True):
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
                user_message="Mixing your intro...",
                session_id=self.session_id,
                debug_message="Rendering intro segment with crossfade and TTS overlay",
            )
            
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
                self.songs_since_last_speech += 1
                
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
            from backend_v2.audio.mix import create_dj_mix
            
            # Need a current song to transition from
            if not self.current_song:
                logger.warning("No current song for mix segment")
                await asyncio.sleep(5)
                return
            
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
                    use_intent_flow=True  # Enable new catalog-based flow
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
            if should_dj_speak(bundle, self.songs_since_last_speech, is_intro=False):
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
                        self.banter_history.append(script)
                        self.songs_since_last_speech = 0
                        
                        await emitter.emit_dj_says(
                            user_id=self.user_id,
                            script=script,
                        )
                
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
            
            result = await asyncio.to_thread(
                create_dj_mix,
                song1_path=prev_song_path,
                song2_path=song_path,
                transition_type=transition.get("transition_type", "crossfade"),
                tts_path=tts_path,
                bpm_a=bpm_a,
                bpm_b=bpm_b,
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
                self.songs_since_last_speech += 1
                
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
