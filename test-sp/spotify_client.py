"""Spotify API client using SpotAPI for authentication and data fetching."""
import logging
from typing import Dict, Any, Optional, List
import os

try:
    from spotapi import Login, Config, NoopLogger, JSONSaver, User, PrivatePlaylist, Song, Artist
except ImportError:
    raise ImportError(
        "spotapi is not installed. Install it with: pip install spotapi"
    )

logger = logging.getLogger("spotify-test.spotify")


class SpotifyClient:
    """Client for Spotify API using SpotAPI library."""
    
    def __init__(self, email: str, password: str, session_save_path: str = "spotify_session.json"):
        """Initialize Spotify client.
        
        Args:
            email: Spotify account email
            password: Spotify account password
            session_save_path: Path to save session for reuse
        """
        self.email = email
        self.password = password
        self.session_save_path = session_save_path
        self.login_instance: Optional[Login] = None
        self._authenticated = False
    
    def authenticate(self, cookies: Optional[Dict[str, str]] = None) -> bool:
        """Authenticate with Spotify using SpotAPI.
        
        Args:
            cookies: Optional cookies dict from browser session to skip CAPTCHA.
                    Format: {"cookie_name": "cookie_value", ...}
                    Get these from browser DevTools after logging into Spotify.
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Try to load existing session first
            if os.path.exists(self.session_save_path):
                try:
                    import json
                    with open(self.session_save_path, 'r') as f:
                        session_data = json.load(f)
                    
                    # Check if session has cookies
                    if session_data.get('cookies'):
                        saver = JSONSaver()
                        # Create a temporary file with session data for from_saver
                        temp_session = {
                            "identifier": session_data.get('identifier', self.email),
                            "cookies": session_data['cookies']
                        }
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                            json.dump(temp_session, tmp)
                            tmp_path = tmp.name
                        
                        try:
                            self.login_instance = Login.from_saver(saver, tmp_path)
                            if self.login_instance:
                                logger.info("Loaded existing session from cookies")
                                self._authenticated = True
                                os.unlink(tmp_path)
                                return True
                        except Exception as e:
                            logger.warning(f"Failed to load session: {e}")
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to load session file: {e}, will create new login")
            
            # If cookies provided, use them directly
            if cookies:
                logger.info("Using provided cookies for authentication")
                import json
                
                # Prepare session data in SpotAPI format
                session_data = {
                    "identifier": self.email,
                    "cookies": cookies
                }
                
                # Save to session file first
                with open(self.session_save_path, 'w') as f:
                    json.dump(session_data, f)
                
                try:
                    # Load session using JSONSaver
                    saver = JSONSaver()
                    # JSONSaver should load from the file we just created
                    # Login.from_saver expects the saver to have the data
                    self.login_instance = Login.from_saver(saver, self.session_save_path)
                    
                    if self.login_instance:
                        logger.info("Successfully authenticated using cookies")
                        self._authenticated = True
                        return True
                    else:
                        logger.error("Login.from_saver returned None")
                        return False
                except Exception as e:
                    logger.error(f"Failed to authenticate with cookies: {e}")
                    logger.error(f"Error type: {type(e).__name__}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    # Try alternative: create Login and manually set cookies
                    try:
                        logger.info("Trying alternative cookie import method...")
                        cfg = Config(logger=NoopLogger())
                        self.login_instance = Login(cfg, "", email=self.email)
                        # Try to set cookies directly if possible
                        if hasattr(self.login_instance, 'base') and hasattr(self.login_instance.base, 'cookies'):
                            self.login_instance.base.cookies.update(cookies)
                            self._authenticated = True
                            logger.info("Successfully set cookies manually")
                            return True
                    except Exception as e2:
                        logger.error(f"Alternative method also failed: {e2}")
                    return False
            
            # Try username/password login (may require CAPTCHA)
            logger.info("Attempting username/password authentication...")
            logger.warning("Note: This may require CAPTCHA solving. Consider using cookie import instead.")
            
            cfg = Config(
                logger=NoopLogger(),
                # Note: CAPTCHA solver can be added here if needed
                # from spotapi.utils.solver_clients import Capsolver
                # solver=Capsolver("YOUR_API_KEY", proxy="YOUR_PROXY")
            )
            
            self.login_instance = Login(cfg, self.password, email=self.email)
            self.login_instance.login()
            
            # Save session for future use
            import json
            session_data = {
                "identifier": self.email,
                "cookies": self.login_instance.base.cookies if hasattr(self.login_instance, 'base') and hasattr(self.login_instance.base, 'cookies') else {}
            }
            with open(self.session_save_path, 'w') as f:
                json.dump(session_data, f)
            
            self._authenticated = True
            logger.info("Successfully authenticated with Spotify")
            return True
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            logger.error("\n" + "="*60)
            logger.error("AUTHENTICATION TROUBLESHOOTING:")
            logger.error("="*60)
            logger.error("Spotify may require CAPTCHA solving. Options:")
            logger.error("1. Import cookies from browser:")
            logger.error("   - Log into Spotify in your browser")
            logger.error("   - Open DevTools (F12) > Application/Storage > Cookies")
            logger.error("   - Copy cookies as dict: {'sp_dc': '...', 'sp_key': '...', etc.}")
            logger.error("   - Use: client.authenticate(cookies={'sp_dc': '...', ...})")
            logger.error("2. Use CAPTCHA solver service (requires API key)")
            logger.error("="*60)
            self._authenticated = False
            return False
    
    def get_user_profile(self) -> Optional[Dict[str, Any]]:
        """Get current user's profile.
        
        Returns:
            User profile dictionary or None on error
        """
        if not self._authenticated or not self.login_instance:
            logger.error("Not authenticated")
            return None
        
        try:
            user = User(self.login_instance)
            # SpotAPI User class methods may vary - adjust based on actual API
            # This is a placeholder - actual implementation depends on SpotAPI's User class
            profile = {
                "email": self.email,
                "authenticated": True
            }
            
            # Try to get additional user info if available
            if hasattr(user, 'get_profile'):
                profile.update(user.get_profile())
            elif hasattr(user, 'profile'):
                profile.update(user.profile)
            
            return profile
            
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            return None
    
    def get_user_playlists(self) -> List[Dict[str, Any]]:
        """Get user's playlists.
        
        Returns:
            List of playlist dictionaries
        """
        if not self._authenticated or not self.login_instance:
            logger.error("Not authenticated")
            return []
        
        try:
            playlist_client = PrivatePlaylist(self.login_instance)
            playlists = []
            
            # SpotAPI may have different methods - adjust based on actual API
            if hasattr(playlist_client, 'get_playlists'):
                playlists = playlist_client.get_playlists()
            elif hasattr(playlist_client, 'list_playlists'):
                playlists = playlist_client.list_playlists()
            elif hasattr(playlist_client, 'playlists'):
                playlists = playlist_client.playlists
            
            # Normalize playlist data
            normalized = []
            for playlist in playlists:
                if isinstance(playlist, dict):
                    normalized.append(playlist)
                else:
                    # Convert to dict if needed
                    normalized.append({
                        "id": getattr(playlist, 'id', None),
                        "name": getattr(playlist, 'name', None),
                        "description": getattr(playlist, 'description', None),
                        "tracks_count": getattr(playlist, 'tracks_count', 0)
                    })
            
            logger.info(f"Retrieved {len(normalized)} playlists")
            return normalized
            
        except Exception as e:
            logger.error(f"Failed to get playlists: {e}")
            return []
    
    def get_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        """Get tracks from a specific playlist.
        
        Args:
            playlist_id: Spotify playlist ID
            
        Returns:
            List of track dictionaries
        """
        if not self._authenticated or not self.login_instance:
            logger.error("Not authenticated")
            return []
        
        try:
            playlist_client = PrivatePlaylist(self.login_instance)
            tracks = []
            
            # Get tracks from playlist
            if hasattr(playlist_client, 'get_playlist_tracks'):
                tracks = playlist_client.get_playlist_tracks(playlist_id)
            elif hasattr(playlist_client, 'get_tracks'):
                tracks = playlist_client.get_tracks(playlist_id)
            
            # Normalize track data
            normalized = []
            for track in tracks:
                if isinstance(track, dict):
                    normalized.append(track)
                else:
                    normalized.append({
                        "id": getattr(track, 'id', None),
                        "name": getattr(track, 'name', None),
                        "artist": getattr(track, 'artist', None),
                        "album": getattr(track, 'album', None)
                    })
            
            return normalized
            
        except Exception as e:
            logger.error(f"Failed to get playlist tracks: {e}")
            return []
    
    def get_top_tracks_from_playlists(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Extract top tracks from user's playlists (since direct top tracks may not be available).
        
        Args:
            limit: Maximum number of tracks to return
            
        Returns:
            List of track dictionaries
        """
        playlists = self.get_user_playlists()
        all_tracks = []
        track_counts = {}
        
        # Collect all tracks from playlists
        for playlist in playlists[:20]:  # Limit to first 20 playlists
            playlist_id = playlist.get('id')
            if playlist_id:
                tracks = self.get_playlist_tracks(playlist_id)
                for track in tracks:
                    track_id = track.get('id') or track.get('name', '')
                    if track_id:
                        if track_id not in track_counts:
                            track_counts[track_id] = 0
                            all_tracks.append(track)
                        track_counts[track_id] += 1
        
        # Sort by frequency and return top tracks
        sorted_tracks = sorted(all_tracks, key=lambda t: track_counts.get(t.get('id') or t.get('name', ''), 0), reverse=True)
        return sorted_tracks[:limit]
    
    def get_top_artists_from_playlists(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Extract top artists from user's playlists.
        
        Args:
            limit: Maximum number of artists to return
            
        Returns:
            List of artist dictionaries
        """
        tracks = self.get_top_tracks_from_playlists(limit=200)  # Get more tracks to analyze
        artist_counts = {}
        artists = []
        
        # Count artist occurrences
        for track in tracks:
            artist_name = track.get('artist') or track.get('artists', [{}])[0].get('name', '') if isinstance(track.get('artists'), list) else ''
            if artist_name:
                if artist_name not in artist_counts:
                    artist_counts[artist_name] = 0
                    artists.append({
                        "name": artist_name,
                        "genres": track.get('genres', [])
                    })
                artist_counts[artist_name] += 1
        
        # Sort by frequency
        sorted_artists = sorted(artists, key=lambda a: artist_counts.get(a['name'], 0), reverse=True)
        return sorted_artists[:limit]
    
    def aggregate_data(self) -> Dict[str, Any]:
        """Aggregate all Spotify data for AI analysis.
        
        Returns:
            Dictionary containing profile, playlists, tracks, and artists
        """
        logger.info("Aggregating Spotify data...")
        
        profile = self.get_user_profile()
        playlists = self.get_user_playlists()
        tracks = self.get_top_tracks_from_playlists(limit=100)
        artists = self.get_top_artists_from_playlists(limit=50)
        
        return {
            "profile": profile or {},
            "playlists": playlists,
            "top_tracks": tracks,
            "top_artists": artists,
            "summary": {
                "total_playlists": len(playlists),
                "total_tracks": len(tracks),
                "total_artists": len(artists)
            }
        }

