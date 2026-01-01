"""SQLite database operations for storing Spotify data and enriched results."""
import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger("spotify-test.database")


class SpotifyDatabase:
    """Manages SQLite database for Spotify test data."""
    
    def __init__(self, db_path: str = "test_sp.db"):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Create database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create spotify_sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spotify_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_email TEXT,
                session_token_hash TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migrate existing tables to add token columns if they don't exist
        try:
            cursor.execute("SELECT access_token FROM spotify_sessions LIMIT 1")
        except sqlite3.OperationalError:
            # Column doesn't exist, add it
            logger.info("Migrating database: adding token columns to spotify_sessions")
            try:
                cursor.execute("ALTER TABLE spotify_sessions ADD COLUMN access_token TEXT")
            except sqlite3.OperationalError:
                pass  # Column might already exist
        
        try:
            cursor.execute("SELECT refresh_token FROM spotify_sessions LIMIT 1")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE spotify_sessions ADD COLUMN refresh_token TEXT")
            except sqlite3.OperationalError:
                pass
        
        try:
            cursor.execute("SELECT expires_at FROM spotify_sessions LIMIT 1")
        except sqlite3.OperationalError:
            try:
                cursor.execute("ALTER TABLE spotify_sessions ADD COLUMN expires_at TIMESTAMP")
            except sqlite3.OperationalError:
                pass
        
        # Create spotify_raw_data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spotify_raw_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                data_type TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES spotify_sessions(id)
            )
        """)
        
        # Create user_profile table (detailed profile info)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                spotify_id TEXT,
                display_name TEXT,
                email TEXT,
                country TEXT,
                product TEXT,
                followers_count INTEGER,
                images_json TEXT,
                external_urls_json TEXT,
                profile_data_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES spotify_sessions(id),
                UNIQUE(session_id)
            )
        """)
        
        # Create top_artists table (with time_range)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS top_artists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                time_range TEXT NOT NULL,
                artist_id TEXT,
                artist_name TEXT,
                popularity INTEGER,
                genres_json TEXT,
                images_json TEXT,
                external_urls_json TEXT,
                followers_count INTEGER,
                rank INTEGER,
                artist_data_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES spotify_sessions(id)
            )
        """)
        
        # Create top_tracks table (with time_range)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS top_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                time_range TEXT NOT NULL,
                track_id TEXT,
                track_name TEXT,
                artist_names TEXT,
                album_name TEXT,
                popularity INTEGER,
                duration_ms INTEGER,
                explicit BOOLEAN,
                preview_url TEXT,
                external_urls_json TEXT,
                rank INTEGER,
                track_data_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES spotify_sessions(id)
            )
        """)
        
        # Create recently_played table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recently_played (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                track_id TEXT,
                track_name TEXT,
                artist_names TEXT,
                album_name TEXT,
                played_at TIMESTAMP NOT NULL,
                context_type TEXT,
                context_uri TEXT,
                track_data_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES spotify_sessions(id)
            )
        """)
        
        # Create playlists table (detailed playlist info)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                playlist_id TEXT,
                playlist_name TEXT,
                owner_id TEXT,
                owner_name TEXT,
                description TEXT,
                public BOOLEAN,
                collaborative BOOLEAN,
                tracks_count INTEGER,
                followers_count INTEGER,
                images_json TEXT,
                external_urls_json TEXT,
                playlist_data_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES spotify_sessions(id)
            )
        """)
        
        # Create enriched_data table (expanded)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enriched_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                favorite_artists_json TEXT,
                favorite_songs_json TEXT,
                last_listened_to_json TEXT,
                top_played_json TEXT,
                user_profile_summary_json TEXT,
                playlist_analysis_json TEXT,
                music_preferences_json TEXT,
                listening_habits_json TEXT,
                genres_analysis_json TEXT,
                mood_analysis_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES spotify_sessions(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_session(self, user_id: Optional[str], user_email: Optional[str]) -> int:
        """Create a new Spotify session.
        
        Args:
            user_id: Spotify user ID
            user_email: User email address
            
        Returns:
            Session ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO spotify_sessions (user_id, user_email)
            VALUES (?, ?)
        """, (user_id, user_email))
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return session_id
    
    def save_raw_data(self, session_id: int, data_type: str, data: Dict[str, Any]):
        """Save raw Spotify data.
        
        Args:
            session_id: Session ID
            data_type: Type of data (profile, playlists, tracks, artists)
            data: Raw data dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO spotify_raw_data (session_id, data_type, raw_json)
            VALUES (?, ?, ?)
        """, (session_id, data_type, json.dumps(data)))
        conn.commit()
        conn.close()
    
    def save_enriched_data(self, session_id: int, preferences: Dict[str, Any], profile_summary: Dict[str, Any]):
        """Save enriched data from AI analysis.
        
        Args:
            session_id: Session ID
            preferences: Music preferences dictionary
            profile_summary: Profile summary dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO enriched_data (session_id, preferences_json, profile_summary_json)
            VALUES (?, ?, ?)
        """, (session_id, json.dumps(preferences), json.dumps(profile_summary)))
        conn.commit()
        conn.close()
    
    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get session information.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session dictionary or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, user_email, created_at
            FROM spotify_sessions
            WHERE id = ?
        """, (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "user_id": row[1],
                "user_email": row[2],
                "created_at": row[3]
            }
        return None
    
    def update_session_tokens(
        self,
        session_id: int,
        access_token: str,
        refresh_token: Optional[str],
        expires_at: datetime
    ) -> bool:
        """Update or set tokens for a session.
        
        Args:
            session_id: Session ID
            access_token: OAuth access token
            refresh_token: OAuth refresh token (optional)
            expires_at: Token expiration timestamp
            
        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE spotify_sessions
            SET access_token = ?, refresh_token = ?, expires_at = ?
            WHERE id = ?
        """, (access_token, refresh_token, expires_at.isoformat(), session_id))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def get_session_tokens(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get tokens for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Dictionary with access_token, refresh_token, expires_at or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT access_token, refresh_token, expires_at
            FROM spotify_sessions
            WHERE id = ?
        """, (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:  # access_token exists
            expires_at = None
            if row[2]:
                try:
                    expires_at = datetime.fromisoformat(row[2])
                except (ValueError, TypeError):
                    pass
            
            return {
                "access_token": row[0],
                "refresh_token": row[1],
                "expires_at": expires_at
            }
        return None
    
    def save_user_profile(self, session_id: int, profile_data: Dict[str, Any]) -> bool:
        """Save detailed user profile data.
        
        Args:
            session_id: Session ID
            profile_data: User profile dictionary from Spotify API
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_profile 
            (session_id, spotify_id, display_name, email, country, product, 
             followers_count, images_json, external_urls_json, profile_data_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            session_id,
            profile_data.get('id'),
            profile_data.get('display_name'),
            profile_data.get('email'),
            profile_data.get('country'),
            profile_data.get('product'),
            profile_data.get('followers', {}).get('total') if isinstance(profile_data.get('followers'), dict) else None,
            json.dumps(profile_data.get('images', [])),
            json.dumps(profile_data.get('external_urls', {})),
            json.dumps(profile_data)
        ))
        conn.commit()
        conn.close()
        return True
    
    def save_top_artists(self, session_id: int, time_range: str, artists: List[Dict[str, Any]]) -> bool:
        """Save top artists for a time range.
        
        Args:
            session_id: Session ID
            time_range: Time range (short_term, medium_term, long_term)
            artists: List of artist dictionaries from Spotify API
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete existing artists for this time range
        cursor.execute("DELETE FROM top_artists WHERE session_id = ? AND time_range = ?", (session_id, time_range))
        
        for rank, artist in enumerate(artists, 1):
            cursor.execute("""
                INSERT INTO top_artists 
                (session_id, time_range, artist_id, artist_name, popularity, genres_json, 
                 images_json, external_urls_json, followers_count, rank, artist_data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                time_range,
                artist.get('id'),
                artist.get('name'),
                artist.get('popularity'),
                json.dumps(artist.get('genres', [])),
                json.dumps(artist.get('images', [])),
                json.dumps(artist.get('external_urls', {})),
                artist.get('followers', {}).get('total') if isinstance(artist.get('followers'), dict) else None,
                rank,
                json.dumps(artist)
            ))
        
        conn.commit()
        conn.close()
        return True
    
    def save_top_tracks(self, session_id: int, time_range: str, tracks: List[Dict[str, Any]]) -> bool:
        """Save top tracks for a time range.
        
        Args:
            session_id: Session ID
            time_range: Time range (short_term, medium_term, long_term)
            tracks: List of track dictionaries from Spotify API
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete existing tracks for this time range
        cursor.execute("DELETE FROM top_tracks WHERE session_id = ? AND time_range = ?", (session_id, time_range))
        
        for rank, track in enumerate(tracks, 1):
            artist_names = ", ".join([a.get('name', '') for a in track.get('artists', [])])
            cursor.execute("""
                INSERT INTO top_tracks 
                (session_id, time_range, track_id, track_name, artist_names, album_name, 
                 popularity, duration_ms, explicit, preview_url, external_urls_json, rank, track_data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                time_range,
                track.get('id'),
                track.get('name'),
                artist_names,
                track.get('album', {}).get('name') if isinstance(track.get('album'), dict) else None,
                track.get('popularity'),
                track.get('duration_ms'),
                track.get('explicit', False),
                track.get('preview_url'),
                json.dumps(track.get('external_urls', {})),
                rank,
                json.dumps(track)
            ))
        
        conn.commit()
        conn.close()
        return True
    
    def save_recently_played(self, session_id: int, recently_played_items: List[Dict[str, Any]]) -> bool:
        """Save recently played tracks.
        
        Args:
            session_id: Session ID
            recently_played_items: List of recently played items from Spotify API
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete existing recently played for this session
        cursor.execute("DELETE FROM recently_played WHERE session_id = ?", (session_id,))
        
        for item in recently_played_items:
            track = item.get('track', {})
            artist_names = ", ".join([a.get('name', '') for a in track.get('artists', [])])
            context = item.get('context', {})
            
            cursor.execute("""
                INSERT INTO recently_played 
                (session_id, track_id, track_name, artist_names, album_name, played_at, 
                 context_type, context_uri, track_data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                track.get('id'),
                track.get('name'),
                artist_names,
                track.get('album', {}).get('name') if isinstance(track.get('album'), dict) else None,
                item.get('played_at'),
                context.get('type') if isinstance(context, dict) else None,
                context.get('uri') if isinstance(context, dict) else None,
                json.dumps(item)
            ))
        
        conn.commit()
        conn.close()
        return True
    
    def save_playlists(self, session_id: int, playlists: List[Dict[str, Any]]) -> bool:
        """Save user playlists.
        
        Args:
            session_id: Session ID
            playlists: List of playlist dictionaries from Spotify API
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete existing playlists for this session
        cursor.execute("DELETE FROM playlists WHERE session_id = ?", (session_id,))
        
        for playlist in playlists:
            owner = playlist.get('owner', {})
            cursor.execute("""
                INSERT INTO playlists 
                (session_id, playlist_id, playlist_name, owner_id, owner_name, description, 
                 public, collaborative, tracks_count, followers_count, images_json, 
                 external_urls_json, playlist_data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                playlist.get('id'),
                playlist.get('name'),
                owner.get('id') if isinstance(owner, dict) else None,
                owner.get('display_name') if isinstance(owner, dict) else None,
                playlist.get('description'),
                playlist.get('public', False),
                playlist.get('collaborative', False),
                playlist.get('tracks', {}).get('total') if isinstance(playlist.get('tracks'), dict) else 0,
                playlist.get('followers', {}).get('total') if isinstance(playlist.get('followers'), dict) else 0,
                json.dumps(playlist.get('images', [])),
                json.dumps(playlist.get('external_urls', {})),
                json.dumps(playlist)
            ))
        
        conn.commit()
        conn.close()
        return True
    
    def save_enriched_data_expanded(
        self,
        session_id: int,
        enriched_data: Dict[str, Any]
    ) -> bool:
        """Save expanded enriched data from AI analysis.
        
        Args:
            session_id: Session ID
            enriched_data: Dictionary with all enriched data fields
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO enriched_data 
            (session_id, favorite_artists_json, favorite_songs_json, last_listened_to_json,
             top_played_json, user_profile_summary_json, playlist_analysis_json,
             music_preferences_json, listening_habits_json, genres_analysis_json, mood_analysis_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            session_id,
            json.dumps(enriched_data.get('favorite_artists', [])),
            json.dumps(enriched_data.get('favorite_songs', [])),
            json.dumps(enriched_data.get('last_listened_to', [])),
            json.dumps(enriched_data.get('top_played', {})),
            json.dumps(enriched_data.get('user_profile_summary', {})),
            json.dumps(enriched_data.get('playlist_analysis', {})),
            json.dumps(enriched_data.get('music_preferences', {})),
            json.dumps(enriched_data.get('listening_habits', {})),
            json.dumps(enriched_data.get('genres_analysis', {})),
            json.dumps(enriched_data.get('mood_analysis', {}))
        ))
        conn.commit()
        conn.close()
        return True

