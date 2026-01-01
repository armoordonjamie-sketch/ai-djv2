"""
RAG Index - Vector index management for track discovery.

This module handles:
1. Building vector index from track catalog
2. Incremental index updates
3. Index persistence
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai-dj.rag.index")

# Global index instance
_vectorstore = None
_index_loaded = False


def get_vectorstore():
    """
    Get or load the vector store.
    
    Lazy-loads from disk if available, otherwise returns None.
    """
    global _vectorstore, _index_loaded
    
    if _index_loaded:
        return _vectorstore
    
    # Try to load from disk
    index_path = os.environ.get("LANGGRAPH_RAG_INDEX_PATH", "data/rag_index")
    
    if os.path.exists(index_path):
        try:
            from langchain_community.vectorstores import FAISS
            from langchain_openai import OpenAIEmbeddings
            
            embeddings = _get_embeddings()
            _vectorstore = FAISS.load_local(
                index_path,
                embeddings,
                allow_dangerous_deserialization=True,
            )
            _index_loaded = True
            logger.info(f"Loaded vector index from {index_path}")
            return _vectorstore
            
        except ImportError:
            logger.warning("FAISS or langchain not available")
        except Exception as e:
            logger.warning(f"Failed to load index: {e}")
    
    _index_loaded = True  # Mark as attempted
    return None


def _get_embeddings():
    """
    Get embeddings model for vectorization.
    
    Uses OpenRouter's embedding endpoint.
    """
    from langchain_openai import OpenAIEmbeddings
    
    return OpenAIEmbeddings(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        model="openai/text-embedding-3-small",
    )


async def build_index(force_rebuild: bool = False) -> bool:
    """
    Build or rebuild the vector index from database.
    
    Args:
        force_rebuild: If True, rebuild even if index exists
        
    Returns:
        True if successful
    """
    global _vectorstore, _index_loaded
    
    index_path = os.environ.get("LANGGRAPH_RAG_INDEX_PATH", "data/rag_index")
    
    # Check if rebuild needed
    if not force_rebuild and os.path.exists(index_path):
        logger.info("Index exists, skipping rebuild (use force_rebuild=True to rebuild)")
        return True
    
    logger.info("Building RAG index from database...")
    
    try:
        from langchain_community.vectorstores import FAISS
        from langchain.schema import Document
        from backend_v2.db.session import get_db_session
        from backend_v2.models.existing import Song, SongFeatures
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        embeddings = _get_embeddings()
        documents = []
        
        async with get_db_session() as db:
            # Get all songs with features
            result = await db.execute(
                select(Song)
                .options(selectinload(Song.features))
                .where(Song.local_path.isnot(None))
                .limit(10000)  # Cap initial index size
            )
            songs = result.scalars().all()
            
            for song in songs:
                # Build document text
                text_parts = [
                    f"Artist: {song.artist}",
                    f"Title: {song.title}",
                ]
                
                if song.genres:
                    import json
                    try:
                        genres = json.loads(song.genres) if isinstance(song.genres, str) else song.genres
                        text_parts.append(f"Genres: {', '.join(genres)}")
                    except:
                        pass
                
                if song.features:
                    text_parts.append(f"BPM: {song.features.tempo or 'unknown'}")
                    text_parts.append(f"Energy: {song.features.energy or 'unknown'}")
                    text_parts.append(f"Valence: {song.features.valence or 'unknown'}")
                
                text = "\n".join(text_parts)
                
                # Build metadata
                metadata = {
                    "uuid": song.uuid,
                    "title": song.title,
                    "artist": song.artist,
                    "duration_sec": song.duration_sec,
                    "local_path": song.local_path,
                    "artwork_url": song.artwork_url,
                }
                
                if song.features:
                    metadata["bpm"] = song.features.tempo
                    metadata["energy"] = song.features.energy
                    metadata["valence"] = song.features.valence
                    metadata["danceability"] = song.features.danceability
                
                documents.append(Document(page_content=text, metadata=metadata))
        
        if not documents:
            logger.warning("No documents to index")
            return False
        
        logger.info(f"Indexing {len(documents)} documents...")
        
        # Create FAISS index
        _vectorstore = FAISS.from_documents(documents, embeddings)
        
        # Save to disk
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        _vectorstore.save_local(index_path)
        
        _index_loaded = True
        logger.info(f"Index built and saved to {index_path}")
        return True
        
    except ImportError as e:
        logger.warning(f"Required libraries not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Index build failed: {e}")
        return False


async def add_to_index(tracks: List[Dict[str, Any]]) -> bool:
    """
    Add tracks to existing index incrementally.
    
    Args:
        tracks: List of track dicts with uuid, title, artist, etc.
        
    Returns:
        True if successful
    """
    global _vectorstore
    
    if not _vectorstore:
        _vectorstore = get_vectorstore()
    
    if not _vectorstore:
        logger.warning("No index available, building from scratch")
        return await build_index()
    
    try:
        from langchain.schema import Document
        
        documents = []
        for track in tracks:
            text_parts = [
                f"Artist: {track.get('artist', '')}",
                f"Title: {track.get('title', '')}",
            ]
            
            genres = track.get("genres", [])
            if genres:
                text_parts.append(f"Genres: {', '.join(genres)}")
            
            if track.get("bpm"):
                text_parts.append(f"BPM: {track['bpm']}")
            if track.get("energy"):
                text_parts.append(f"Energy: {track['energy']}")
            
            text = "\n".join(text_parts)
            
            documents.append(Document(
                page_content=text,
                metadata={
                    "uuid": track.get("uuid", ""),
                    "title": track.get("title", ""),
                    "artist": track.get("artist", ""),
                    "duration_sec": track.get("duration_sec"),
                    "local_path": track.get("local_path"),
                }
            ))
        
        if documents:
            _vectorstore.add_documents(documents)
            
            # Save updated index
            index_path = os.environ.get("LANGGRAPH_RAG_INDEX_PATH", "data/rag_index")
            _vectorstore.save_local(index_path)
            
            logger.info(f"Added {len(documents)} tracks to index")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to add to index: {e}")
        return False


def get_index_stats() -> Dict[str, Any]:
    """
    Get statistics about the current index.
    """
    vectorstore = get_vectorstore()
    
    if not vectorstore:
        return {"status": "not_loaded", "document_count": 0}
    
    try:
        # FAISS-specific stats
        if hasattr(vectorstore, "index"):
            return {
                "status": "loaded",
                "document_count": vectorstore.index.ntotal,
                "dimension": vectorstore.index.d,
            }
    except:
        pass
    
    return {"status": "loaded", "document_count": "unknown"}
