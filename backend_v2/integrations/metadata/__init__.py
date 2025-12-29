# Metadata providers package
from backend_v2.integrations.metadata.musicbrainz import MusicBrainzClient, get_musicbrainz_client
from backend_v2.integrations.metadata.apple_music import AppleMusicClient, get_apple_music_client
from backend_v2.integrations.metadata.enrichment import (
    MetadataEnrichmentService,
    get_metadata_service,
    enrich_song_metadata,
)

__all__ = [
    "MusicBrainzClient",
    "get_musicbrainz_client",
    "AppleMusicClient", 
    "get_apple_music_client",
    "MetadataEnrichmentService",
    "get_metadata_service",
    "enrich_song_metadata",
]

