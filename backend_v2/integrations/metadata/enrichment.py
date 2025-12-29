"""Unified metadata enrichment service.

Combines MusicBrainz, Apple Music, and Deezer to enrich track metadata:
- MusicBrainz: ISRCs, MBIDs, canonical IDs
- Apple Music: Artwork, genres
- Deezer: Fallback artwork, BPM
- Cover Art Archive: Fallback artwork from MusicBrainz releases

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

from backend_v2.integrations.metadata.musicbrainz import get_musicbrainz_client
from backend_v2.integrations.metadata.apple_music import get_apple_music_client
from backend_v2.integrations.metadata.deezer_metadata import get_deezer_metadata_client
from backend_v2.models.existing import Song
from backend_v2.db.session import get_db_session

logger = logging.getLogger("ai-dj.metadata")


class MetadataEnrichmentService:
    """Service for enriching song metadata from multiple sources."""
    
    def __init__(self):
        self.mb_client = get_musicbrainz_client()
        self.am_client = get_apple_music_client()
        self.dz_client = get_deezer_metadata_client()
    
    async def enrich_song(
        self,
        song_uuid: str,
        artist: str,
        title: str,
        isrc: Optional[str] = None,
        audio_path: Optional[str] = None,
        update_db: bool = True,
    ) -> Dict[str, Any]:
        """Enrich song metadata from all sources.
        
        Args:
            song_uuid: Song UUID in our database
            artist: Artist name
            title: Song title
            isrc: Optional existing ISRC
            update_db: Whether to persist enrichment to database
            
        Returns:
            Dict with all enriched metadata
        """
        enrichment = {
            "song_uuid": song_uuid,
            "artist": artist,
            "title": title,
        }
        
        # Run both lookups in parallel
        mb_task = self._enrich_from_musicbrainz(artist, title, isrc)
        am_task = self._enrich_from_apple_music(artist, title)
        
        mb_result, am_result = await asyncio.gather(
            mb_task,
            am_task,
            return_exceptions=True,
        )
        
        # Merge MusicBrainz results
        if isinstance(mb_result, dict):
            enrichment.update({
                "isrc": mb_result.get("isrc") or isrc,
                "recording_mbid": mb_result.get("recording_mbid"),
                "release_mbid": mb_result.get("release_mbid"),
                "artist_mbid": mb_result.get("artist_mbid"),
                "mb_tags": mb_result.get("tags", []),
            })
        elif isinstance(mb_result, Exception):
            logger.error(f"MusicBrainz enrichment failed: {mb_result}")
        
        # Merge Apple Music results
        if isinstance(am_result, dict):
            enrichment.update({
                "apple_song_id": am_result.get("apple_song_id"),
                "artwork_url": am_result.get("artwork_url"),
                "genres": am_result.get("genres", []),
                "explicit": am_result.get("explicit"),
            })
        elif isinstance(am_result, Exception):
            logger.error(f"Apple Music enrichment failed: {am_result}")
        
        # Try Cover Art Archive as fallback for artwork
        if not enrichment.get("artwork_url") and enrichment.get("release_mbid"):
            caa_url = await self._get_cover_art_archive(enrichment["release_mbid"])
            if caa_url:
                enrichment["artwork_url"] = caa_url

        # Try Deezer as final fallback for artwork and BPM
        if not enrichment.get("artwork_url"):
            dz_result = await self._enrich_from_deezer(artist, title)
            if dz_result:
                if dz_result.get("artwork_url"):
                    enrichment["artwork_url"] = dz_result["artwork_url"]
                if dz_result.get("bpm") and not enrichment.get("features", {}).get("tempo"):
                    if "features" not in enrichment:
                        enrichment["features"] = {}
                    enrichment["features"]["tempo"] = dz_result["bpm"]
                if dz_result.get("deezer_id"):
                    enrichment["deezer_id"] = dz_result["deezer_id"]

        # Extract audio features from file if available
        audio_features = await self._extract_audio_features(audio_path)
        if audio_features:
            enrichment["features"] = audio_features

        # Fill missing features with LLM estimates (optional)
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
            await self._persist_enrichment(song_uuid, enrichment)
        
        logger.info(f"Enriched {artist} - {title}: "
                   f"ISRC={enrichment.get('isrc')}, "
                   f"artwork={'yes' if enrichment.get('artwork_url') else 'no'}, "
                   f"genres={len(enrichment.get('genres', []))}")
        
        return enrichment

    async def _extract_audio_features(
        self,
        audio_path: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Extract audio features from a local file (librosa optional)."""
        if not audio_path or not os.path.exists(audio_path):
            return None
        try:
            from backend_v2.audio.features import extract_audio_features
            return await asyncio.to_thread(extract_audio_features, audio_path)
        except Exception as e:
            logger.warning(f"Audio feature extraction failed: {e}")
            return None
    
    async def _enrich_from_musicbrainz(
        self,
        artist: str,
        title: str,
        isrc: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get MusicBrainz metadata."""
        if not self.mb_client.enabled:
            return None
        
        return await self.mb_client.match_track(artist, title, isrc)
    
    async def _enrich_from_apple_music(
        self,
        artist: str,
        title: str,
    ) -> Optional[Dict[str, Any]]:
        """Get Apple Music metadata."""
        if not self.am_client.enabled:
            return None
        
        return await self.am_client.enrich_track(artist, title)
    
    async def _enrich_from_deezer(
        self,
        artist: str,
        title: str,
    ) -> Optional[Dict[str, Any]]:
        """Get Deezer metadata (fallback for artwork and BPM)."""
        try:
            return await self.dz_client.get_track_metadata(artist, title)
        except Exception as e:
            logger.debug(f"Deezer enrichment failed: {e}")
            return None
    
    async def _get_cover_art_archive(
        self,
        release_mbid: str,
    ) -> Optional[str]:
        """Get artwork from Cover Art Archive (MusicBrainz).
        
        Cover Art Archive is a community database of album art.
        """
        import httpx
        
        url = f"https://coverartarchive.org/release/{release_mbid}/front-500"
        
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.head(url, timeout=10.0)
                
                if response.status_code == 200:
                    # URL is valid, return it
                    return url
                elif response.status_code == 307:
                    # Redirect to actual image
                    return response.headers.get("location", url)
        except Exception as e:
            logger.debug(f"Cover Art Archive lookup failed: {e}")
        
        return None
    
    async def _estimate_features_with_llm(
        self,
        artist: str,
        title: str,
        genres: list,
    ) -> Optional[Dict[str, float]]:
        """Estimate audio features using LLM."""
        from backend_v2.integrations.openrouter import get_openrouter_client
        client = get_openrouter_client()
        if not client.enabled:
            return None
            
        return await client.estimate_song_features(artist, title, genres)

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
    ) -> None:
        """Persist enrichment data to database."""
        import json
        from backend_v2.models.existing import SongFeatures
        
        try:
            async with get_db_session() as db:
                # 1. Update Song Metadata
                update_data = {}
                
                if enrichment.get("isrc"):
                    update_data["isrc"] = enrichment["isrc"]
                if enrichment.get("recording_mbid"):
                    update_data["recording_mbid"] = enrichment["recording_mbid"]
                if enrichment.get("release_mbid"):
                    update_data["release_mbid"] = enrichment["release_mbid"]
                if enrichment.get("artist_mbid"):
                    update_data["artist_mbid"] = enrichment["artist_mbid"]
                if enrichment.get("apple_song_id"):
                    update_data["apple_song_id"] = enrichment["apple_song_id"]
                if enrichment.get("artwork_url"):
                    update_data["artwork_url"] = enrichment["artwork_url"]
                if enrichment.get("genres"):
                    update_data["genres"] = json.dumps(enrichment["genres"])
                if enrichment.get("tags") or enrichment.get("mb_tags"):
                    tags = enrichment.get("tags") or enrichment.get("mb_tags", [])
                    update_data["tags"] = json.dumps(tags)
                
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
                
                await db.commit()
                
                logger.info(f"Persisted enrichment for {song_uuid}")
                
        except Exception as e:
            logger.error(f"Failed to persist enrichment for {song_uuid}: {e}")


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
) -> Dict[str, Any]:
    """Convenience function to enrich a song.
    
    Usage:
        enriched = await enrich_song_metadata(uuid, "Artist", "Title")
    """
    service = get_metadata_service()
    return await service.enrich_song(song_uuid, artist, title, isrc, audio_path=audio_path)
