"""Unified metadata enrichment service using Spotify Web API.

Uses Spotify Web API to enrich track metadata:
- Track search and matching
- Artwork URLs (high quality)
- Audio features (energy, valence, tempo, danceability, etc.)
- Genre information
- ISRC codes
- Release dates
- Explicit content flags

Usage:
    service = MetadataEnrichmentService()
    enriched = await service.enrich_song(song_uuid, artist, title)
"""
import logging
import asyncio
import os
from typing import Optional, Dict, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.integrations.metadata.spotify_metadata import get_spotify_metadata_client
from backend_v2.models.existing import Song
from backend_v2.db.session import get_db_session

logger = logging.getLogger("ai-dj.metadata")


class MetadataEnrichmentService:
    """Service for enriching song metadata using Spotify Web API."""
    
    def __init__(self):
        self.spotify_client = get_spotify_metadata_client()
    
    async def enrich_song(
        self,
        song_uuid: str,
        artist: str,
        title: str,
        isrc: Optional[str] = None,
        audio_path: Optional[str] = None,
        update_db: bool = True,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Enrich song metadata from Spotify.
        
        Args:
            song_uuid: Song UUID in our database
            artist: Artist name
            title: Song title
            isrc: Optional existing ISRC (used for better matching)
            audio_path: Path to audio file for feature extraction (fallback if Spotify fails)
            update_db: Whether to persist enrichment to database
            db: Optional database session (prevents nested sessions)
            
        Returns:
            Dict with all enriched metadata
        """
        enrichment = {
            "song_uuid": song_uuid,
            "artist": artist,
            "title": title,
        }
        
        # Get metadata from Spotify
        logger.debug(f"Starting Spotify metadata enrichment for: {artist} - {title}")
        
        if self.spotify_client.enabled:
            spotify_result = await self._enrich_from_spotify(artist, title, isrc)
            if spotify_result:
                enrichment.update({
                    "spotify_id": spotify_result.get("spotify_id"),
                    "isrc": spotify_result.get("isrc") or isrc,
                    "artwork_url": spotify_result.get("artwork_url"),
                    "genres": spotify_result.get("genres", []),
                    "explicit": spotify_result.get("explicit"),
                    "preview_url": spotify_result.get("preview_url"),
                    "album_name": spotify_result.get("album_name"),
                    "release_date": spotify_result.get("release_date"),
                })
                
                # Add audio features from Spotify
                if spotify_result.get("features"):
                    enrichment["features"] = spotify_result["features"]
        
        # Extract audio features from file if Spotify didn't provide them
        if not enrichment.get("features") and audio_path:
            audio_features = await self._extract_audio_features(audio_path)
            if audio_features:
                enrichment["features"] = audio_features
        
        # Fill missing features with LLM estimates (optional fallback)
        if self._needs_llm_features(enrichment.get("features")):
            genres = enrichment.get("genres") or []
            llm_features = await self._estimate_features_with_llm(artist, title, genres)
            if llm_features:
                enrichment["features"] = self._merge_feature_estimates(
                    enrichment.get("features"),
                    llm_features,
                )
        
        # Persist to database
        if update_db:
            try:
                await asyncio.wait_for(
                    self._persist_enrichment(song_uuid, enrichment, db=db),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"Enrichment persistence timed out after 10s")
        
        logger.info(f"Enriched {artist} - {title}: "
                   f"ISRC={enrichment.get('isrc')}, "
                   f"artwork={'yes' if enrichment.get('artwork_url') else 'no'}, "
                   f"features={'yes' if enrichment.get('features') else 'no'}, "
                   f"genres={len(enrichment.get('genres', []))}")
        
        return enrichment

    async def _extract_audio_features(
        self,
        audio_path: Optional[str],
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Extract audio features from a local file (librosa optional).
        
        Args:
            audio_path: Path to audio file
            timeout: Max seconds to wait for extraction (default 30s)
        """
        if not audio_path or not os.path.exists(audio_path):
            return None
        try:
            from backend_v2.audio.features import extract_audio_features
            logger.debug(f"Extracting audio features from: {audio_path}")
            result = await asyncio.wait_for(
                asyncio.to_thread(extract_audio_features, audio_path),
                timeout=timeout
            )
            logger.debug(f"Audio feature extraction complete")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Audio feature extraction timed out after {timeout}s: {audio_path}")
            return None
        except Exception as e:
            logger.warning(f"Audio feature extraction failed: {e}")
            return None
    
    async def _enrich_from_spotify(
        self,
        artist: str,
        title: str,
        isrc: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Optional[Dict[str, Any]]:
        """Get metadata from Spotify Web API."""
        if not self.spotify_client.enabled:
            logger.debug("Spotify metadata client not enabled")
            return None
        
        try:
            return await asyncio.wait_for(
                self.spotify_client.get_track_metadata(artist, title),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Spotify lookup timed out after {timeout}s")
            return None
        except Exception as e:
            logger.warning(f"Spotify enrichment failed: {e}")
            return None
    
    async def _estimate_features_with_llm(
        self,
        artist: str,
        title: str,
        genres: list,
        timeout: float = 15.0,
    ) -> Optional[Dict[str, float]]:
        """Estimate audio features using LLM.
        
        Args:
            artist: Artist name
            title: Song title
            genres: Genre list
            timeout: Max seconds to wait (default 15s)
        """
        from backend_v2.integrations.openrouter import get_openrouter_client
        client = get_openrouter_client()
        if not client.enabled:
            return None
        
        try:
            return await asyncio.wait_for(
                client.estimate_song_features(artist, title, genres),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"LLM feature estimation timed out after {timeout}s")
            return None
        except Exception as e:
            logger.warning(f"LLM feature estimation failed: {e}")
            return None

    def _needs_llm_features(self, features: Optional[Dict[str, Any]]) -> bool:
        """Check if we should fill missing features via LLM."""
        if not features:
            return True
        for key in ("energy", "tempo", "valence", "danceability", "acousticness"):
            if features.get(key) is None:
                return True
        return False

    def _merge_feature_estimates(
        self,
        base: Optional[Dict[str, Any]],
        overlay: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge features, preferring base values when present."""
        merged = dict(base or {})
        for key, value in (overlay or {}).items():
            if merged.get(key) is None and value is not None:
                merged[key] = value
        return merged

    async def _persist_enrichment(
        self,
        song_uuid: str,
        enrichment: Dict[str, Any],
        db: Optional[AsyncSession] = None
    ) -> None:
        """Persist enrichment data to database.
        
        Args:
            song_uuid: Song UUID
            enrichment: Enrichment data dict
            db: Optional database session (if provided, uses it directly)
        """
        import json
        from backend_v2.models.existing import SongFeatures
        
        try:
            # If external session provided, use it directly (no nested session)
            if db is not None:
                await self._persist_with_session(db, song_uuid, enrichment)
                return
            
            # Fallback: Create our own session
            async with get_db_session() as db:
                await self._persist_with_session(db, song_uuid, enrichment)
                await db.commit()
                
            logger.info(f"Persisted enrichment for {song_uuid}")
                
        except Exception as e:
            logger.error(f"Failed to persist enrichment for {song_uuid}: {e}")
    
    async def _persist_with_session(
        self,
        db: AsyncSession,
        song_uuid: str,
        enrichment: Dict[str, Any]
    ) -> None:
        """Internal method to persist enrichment with a provided session."""
        import json
        from backend_v2.models.existing import SongFeatures
        
        # 1. Update Song Metadata
        update_data = {}
        
        if enrichment.get("isrc"):
            update_data["isrc"] = enrichment["isrc"]
        if enrichment.get("spotify_id"):
            # Store Spotify ID in a field if available (or use a generic external_id field)
            # For now, we'll store it in a way that doesn't break existing schema
            pass  # Can add spotify_id field to Song model if needed
        if enrichment.get("artwork_url"):
            update_data["artwork_url"] = enrichment["artwork_url"]
        if enrichment.get("genres"):
            update_data["genres"] = json.dumps(enrichment["genres"])
        if enrichment.get("tags"):
            update_data["tags"] = json.dumps(enrichment["tags"])
        
        if update_data:
            await db.execute(
                update(Song).where(Song.uuid == song_uuid).values(**update_data)
            )
        
        # 2. Update Song Features (if available)
        if enrichment.get("features"):
            feats = enrichment["features"]
            if not any(v is not None for v in feats.values()):
                feats = None
        else:
            feats = None

        if feats:
            # Check if exists
            stmt = select(SongFeatures).where(SongFeatures.song_uuid == song_uuid)
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                for k, v in feats.items():
                    setattr(existing, k, v)
            else:
                new_features = SongFeatures(
                    song_uuid=song_uuid,
                    **feats
                )
                db.add(new_features)


# Singleton
_service: Optional[MetadataEnrichmentService] = None


def get_metadata_service() -> MetadataEnrichmentService:
    """Get the singleton metadata enrichment service."""
    global _service
    if _service is None:
        _service = MetadataEnrichmentService()
    return _service


async def enrich_song_metadata(
    song_uuid: str,
    artist: str,
    title: str,
    isrc: Optional[str] = None,
    audio_path: Optional[str] = None,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Convenience function to enrich a song.
    
    Usage:
        enriched = await enrich_song_metadata(uuid, "Artist", "Title")
    
    Args:
        song_uuid: Song UUID
        artist: Artist name
        title: Song title
        isrc: Optional ISRC
        audio_path: Optional path to audio file
        db: Optional database session (prevents nested sessions)
    """
    service = get_metadata_service()
    return await service.enrich_song(song_uuid, artist, title, isrc, audio_path=audio_path, db=db)
