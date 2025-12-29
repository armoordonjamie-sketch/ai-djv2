"""DJ Session Manager for multi-user streaming.

Manages one active session per user with global caps.
Each session has its own orchestration loop and segment queue.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, Any

from backend_v2.config import MAX_SESSIONS_PER_USER, MAX_SESSIONS_TOTAL

logger = logging.getLogger("ai-dj.session_manager")


class SessionRunner:
    """Per-user DJ session with isolated orchestration."""
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        mood_id: Optional[str] = None,
        context_name: Optional[str] = None,
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.mood_id = mood_id
        self.context_name = context_name  # Renamed from context_id
        self.started_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        
        # Segment queue for this user's stream
        self.segment_queue: asyncio.Queue = asyncio.Queue()
        
        # DJLoop instance
        self.dj_loop: Optional[Any] = None
        
        # Stream state
        self.now_playing: Optional[str] = None
        self.is_running = False
    
    async def start(self):
        """Start the DJ orchestration loop for this session."""
        if self.is_running:
            logger.warning(f"Session {self.session_id} already running")
            return
        
        self.is_running = True
        logger.info(f"Starting session {self.session_id} for user {self.user_id}")
        
        # Create and start actual DJLoop
        from backend_v2.orchestration.loop import DJLoop
        
        self.dj_loop = DJLoop(
            user_id=self.user_id,
            session_id=self.session_id,
            mood_id=self.mood_id,
            context_name=self.context_name,
            segment_queue=self.segment_queue,
        )
        
        await self.dj_loop.start()
        logger.info(f"DJLoop started for session {self.session_id}")
    
    async def stop(self):
        """Stop the DJ orchestration loop."""
        self.is_running = False
        
        if self.dj_loop:
            await self.dj_loop.stop()
            self.dj_loop = None
        
        logger.info(f"Stopped session {self.session_id}")
    
    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
    
    def get_loop_state(self) -> Dict[str, Any]:
        """Get current DJ loop state."""
        if self.dj_loop:
            return self.dj_loop.get_state()
        return {"error": "Loop not running"}




class DJSessionManager:
    """Manages active user sessions with caps and cleanup."""
    
    _instance: Optional["DJSessionManager"] = None
    
    def __init__(self):
        self._sessions: Dict[str, SessionRunner] = {}  # user_id -> SessionRunner
        self._lock = asyncio.Lock()
    
    @classmethod
    def get_instance(cls) -> "DJSessionManager":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @property
    def active_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)
    
    async def start_session(
        self,
        user_id: str,
        mood_id: Optional[str] = None,
        context_name: Optional[str] = None,
        force_new: bool = False,
    ) -> SessionRunner:
        """
        Start or resume a session for a user.
        
        Idempotent: returns existing session if active (unless force_new).
        Enforces MAX_SESSIONS_PER_USER and MAX_SESSIONS_TOTAL.
        """
        async with self._lock:
            # Check for existing session
            existing = self._sessions.get(user_id)
            
            if existing and existing.is_running and not force_new:
                logger.info(f"Returning existing session for user {user_id}")
                existing.touch()
                return existing
            
            # Clean up old session if exists
            if existing:
                await existing.stop()
                del self._sessions[user_id]
            
            # Check global session limit
            if self.active_session_count >= MAX_SESSIONS_TOTAL:
                raise SessionLimitError(
                    f"Global session limit reached ({MAX_SESSIONS_TOTAL})"
                )
            
            # Create new session
            session_id = str(uuid.uuid4())
            session = SessionRunner(
                user_id=user_id,
                session_id=session_id,
                mood_id=mood_id,
                context_name=context_name,
            )

            
            # Start the session
            await session.start()
            
            self._sessions[user_id] = session
            logger.info(
                f"Created session {session_id} for user {user_id}. "
                f"Total active: {self.active_session_count}"
            )
            
            return session
    
    async def stop_session(self, user_id: str) -> bool:
        """Stop a user's session."""
        async with self._lock:
            session = self._sessions.get(user_id)
            if not session:
                return False
            
            await session.stop()
            del self._sessions[user_id]
            
            logger.info(
                f"Stopped session for user {user_id}. "
                f"Total active: {self.active_session_count}"
            )
            return True
    
    def get_session(self, user_id: str) -> Optional[SessionRunner]:
        """Get a user's active session."""
        session = self._sessions.get(user_id)
        if session:
            session.touch()
        return session
    
    async def cleanup_idle_sessions(self, max_idle_minutes: int = 10):
        """Stop sessions that have been idle too long."""
        now = datetime.utcnow()
        idle_threshold = max_idle_minutes * 60  # seconds
        
        to_remove = []
        
        async with self._lock:
            for user_id, session in self._sessions.items():
                idle_seconds = (now - session.last_activity).total_seconds()
                if idle_seconds > idle_threshold:
                    to_remove.append(user_id)
            
            for user_id in to_remove:
                session = self._sessions.pop(user_id, None)
                if session:
                    await session.stop()
                    logger.info(f"Cleaned up idle session for user {user_id}")
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} idle sessions")


class SessionLimitError(Exception):
    """Raised when session limits are exceeded."""
    pass


# Convenience function to get the manager
def get_session_manager() -> DJSessionManager:
    """Get the session manager singleton."""
    return DJSessionManager.get_instance()
