"""
Content Deduplication Engine — Member 2 (RAG + Rules)

Provides SHA-256 content-hash verification to determine whether an incoming
document or file is NEW, MODIFIED, or UNMODIFIED before performing chunking
or vector embedding. Prevents redundant computations and duplicate entries.
"""

import hashlib
from enum import Enum
from typing import Optional, Tuple

from ..models import MemoryRecord
from ..storage.base import MemoryStorage


class IngestionStatus(str, Enum):
    NEW = "NEW"
    MODIFIED = "MODIFIED"
    UNMODIFIED = "UNMODIFIED"


class ContentDeduplicator:
    """
    Evaluates content changes using SHA-256 cryptographic hashes against
    the persistent MemoryStorage backend.
    """

    @staticmethod
    def compute_hash(content: str) -> str:
        """Computes deterministic SHA-256 hash of normalized content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def check_status(
        self,
        storage: MemoryStorage,
        project_id: str,
        source_path: str,
        new_content_hash: str,
    ) -> Tuple[IngestionStatus, Optional[MemoryRecord]]:
        """
        Determines whether the given content requires indexing:
        - NEW: No prior record found for (project_id, source_path).
        - UNMODIFIED: Found existing record with matching content_hash.
        - MODIFIED: Found existing record, but content_hash differs.

        Returns:
            Tuple of (IngestionStatus, existing_record_or_None)
        """
        existing = storage.get_record_by_path(project_id=project_id, source_path=source_path)
        if existing is None:
            return IngestionStatus.NEW, None

        existing_hash = existing.metadata.get("content_hash")
        if existing_hash == new_content_hash:
            return IngestionStatus.UNMODIFIED, existing

        return IngestionStatus.MODIFIED, existing
