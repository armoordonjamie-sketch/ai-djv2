
"""Persistent cache for media analysis (loudness, duration).

Uses sidecar JSON files to store analysis results.
Invalidates based on file size and mtime.
"""
import os
import json
import logging
import time
from typing import Optional, Dict

logger = logging.getLogger("ai-dj.audio.cache")

def _get_cache_path(file_path: str) -> str:
    """Get path to sidecar cache file."""
    return f"{file_path}.analysis.json"

def get_cached_analysis(file_path: str) -> Optional[Dict[str, float]]:
    """Get cached analysis if valid.
    
    Returns None if cache missing or stale.
    """
    if not os.path.exists(file_path):
        return None
        
    cache_path = _get_cache_path(file_path)
    if not os.path.exists(cache_path):
        return None
        
    try:
        # Check staleness
        file_stat = os.stat(file_path)
        cache_stat = os.stat(cache_path)
        
        # If cache is older than file, it's stale
        if cache_stat.st_mtime < file_stat.st_mtime:
            logger.debug(f"Cache stale for {file_path}")
            return None
            
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Verify size matches (extra safety)
        if data.get("file_size") != file_stat.st_size:
            logger.debug(f"Cache size mismatch for {file_path}")
            return None
            
        return data
        
    except Exception as e:
        logger.warning(f"Cache read error for {file_path}: {e}")
        return None

def save_cached_analysis(file_path: str, data: Dict[str, float]):
    """Save analysis to cache."""
    try:
        cache_path = _get_cache_path(file_path)
        file_stat = os.stat(file_path)
        
        cache_data = data.copy()
        cache_data["file_size"] = file_stat.st_size
        cache_data["analyzed_at"] = time.time()
        
        # atomic write not strictly necessary for this use case, but good practice
        # ignoring atomic requirement for simplicity here
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
            
        logger.debug(f"Cached analysis for {file_path}")
        
    except Exception as e:
        logger.warning(f"Cache write error for {file_path}: {e}")
