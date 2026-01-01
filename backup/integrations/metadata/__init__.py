# Metadata providers package - Spotify Web API only
from backend_v2.integrations.metadata.spotify_metadata import (
    SpotifyMetadataClient,
    get_spotify_metadata_client,
)
from backend_v2.integrations.metadata.enrichment import (
    MetadataEnrichmentService,
    get_metadata_service,
    enrich_song_metadata,
)

__all__ = [
    "SpotifyMetadataClient",
    "get_spotify_metadata_client",
    "MetadataEnrichmentService",
    "get_metadata_service",
    "enrich_song_metadata",
]
