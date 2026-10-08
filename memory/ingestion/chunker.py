"""
Deterministic Content Chunker — Member 2 (RAG + Rules)

Splits normalized text into atomic `MemoryChunk` objects while preserving
natural structural boundaries (Markdown headings, code blocks, conversation turns),
precise line-level provenance (start_line, end_line), and SHA-256 content hashes.
"""

import hashlib
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..models import MemoryChunk


class TextChunker:
    """
    Deterministic chunker for markdown, code, documentation, and conversation turns.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        """
        Args:
            chunk_size: Target maximum character length per chunk.
            chunk_overlap: Approximate character overlap when splitting large blocks.
        """
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError(f"chunk_overlap must be in [0, chunk_size), got {chunk_overlap}")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(
        self,
        text: str,
        record_id: str,
        source_type: str = "doc",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryChunk]:
        """
        Splits text into deterministic MemoryChunk objects.

        Args:
            text: Normalized input text.
            record_id: Identifier of the parent MemoryRecord.
            source_type: 'doc' | 'code' | 'conversation' | 'decision'
            metadata: Additional metadata to inherit into each chunk.

        Returns:
            List of MemoryChunk instances with 1-indexed line numbers and hashes.
        """
        if not text or not text.strip():
            return []

        base_meta = dict(metadata or {})
        lines = text.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return []

        # 1. Identify natural boundary splits (line indices, 0-indexed)
        if source_type in ("doc", "markdown"):
            boundary_splits = self._find_markdown_boundaries(lines)
        elif source_type in ("code", "python", "typescript", "javascript"):
            boundary_splits = self._find_code_boundaries(lines)
        elif source_type in ("conversation", "session"):
            boundary_splits = self._find_conversation_boundaries(lines)
        else:
            boundary_splits = self._find_generic_boundaries(lines)

        # 2. Form initial sections from boundaries
        raw_sections: List[tuple[int, int, str]] = []  # (start_line_1idx, end_line_1idx, text)
        for i in range(len(boundary_splits)):
            start_idx = boundary_splits[i]
            end_idx = boundary_splits[i + 1] if i + 1 < len(boundary_splits) else total_lines
            section_lines = lines[start_idx:end_idx]
            section_text = "\n".join(section_lines).strip()
            if section_text:
                raw_sections.append((start_idx + 1, end_idx, section_text))

        # 3. Subdivide large sections or combine small consecutive sections
        sized_chunks: List[tuple[int, int, str]] = []
        for start_line, end_line, sec_text in raw_sections:
            if len(sec_text) <= self.chunk_size:
                sized_chunks.append((start_line, end_line, sec_text))
            else:
                # Sub-split oversized section respecting line numbers
                sub_chunks = self._subdivide_section(lines, start_line, end_line)
                sized_chunks.extend(sub_chunks)

        # If sized_chunks is empty (e.g. only whitespace), fall back to whole content
        if not sized_chunks:
            sized_chunks = [(1, total_lines, text.strip())]

        # 4. Construct MemoryChunk objects with hashes
        result: List[MemoryChunk] = []
        for idx, (s_line, e_line, chunk_content) in enumerate(sized_chunks):
            content_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()
            chunk_meta = dict(base_meta)
            chunk_meta.update({
                "source_type": source_type,
                "char_length": len(chunk_content),
                "line_count": (e_line - s_line + 1),
            })

            result.append(MemoryChunk(
                chunk_id=str(uuid4()),
                record_id=record_id,
                chunk_index=idx,
                content=chunk_content,
                content_hash=content_hash,
                embedding=None,
                start_line=s_line,
                end_line=e_line,
                metadata=chunk_meta,
            ))

        return result

    def _find_markdown_boundaries(self, lines: List[str]) -> List[int]:
        """Detects headers (# , ## , ### ) and major section dividers."""
        boundaries = [0]
        header_pattern = re.compile(r"^(#{1,4}\s+|={3,}|-{3,})")
        for i, line in enumerate(lines):
            if i > 0 and header_pattern.match(line.strip()):
                boundaries.append(i)
        return sorted(list(set(boundaries)))

    def _find_code_boundaries(self, lines: List[str]) -> List[int]:
        """Detects top-level classes, functions, and export blocks."""
        boundaries = [0]
        code_pattern = re.compile(r"^(def\s+|async\s+def\s+|class\s+|export\s+|function\s+|pub\s+fn\s+|interface\s+|struct\s+|@)")
        for i, line in enumerate(lines):
            if i > 0 and code_pattern.match(line):
                boundaries.append(i)
        return sorted(list(set(boundaries)))

    def _find_conversation_boundaries(self, lines: List[str]) -> List[int]:
        """Detects speaker/turn changes in conversations."""
        boundaries = [0]
        turn_pattern = re.compile(r"^(User|Assistant|Human|AI|System|Turn\s+\d+|###\s+Turn):\s*", re.IGNORECASE)
        for i, line in enumerate(lines):
            if i > 0 and turn_pattern.match(line.strip()):
                boundaries.append(i)
        return sorted(list(set(boundaries)))

    def _find_generic_boundaries(self, lines: List[str]) -> List[int]:
        """Detects empty line paragraph separators."""
        boundaries = [0]
        for i, line in enumerate(lines):
            if i > 0 and not line.strip() and (i + 1 < len(lines) and lines[i + 1].strip()):
                boundaries.append(i + 1)
        return sorted(list(set(boundaries)))

    def _subdivide_section(
        self,
        all_lines: List[str],
        start_line_1idx: int,
        end_line_1idx: int,
    ) -> List[tuple[int, int, str]]:
        """Subdivides an oversized block of lines respecting line numbers."""
        sub_chunks: List[tuple[int, int, str]] = []
        cur_lines: List[str] = []
        cur_start = start_line_1idx
        cur_len = 0

        section_lines = all_lines[start_line_1idx - 1 : end_line_1idx]

        for offset, line in enumerate(section_lines):
            line_len = len(line) + 1
            if cur_len + line_len > self.chunk_size and cur_lines:
                chunk_text = "\n".join(cur_lines).strip()
                if chunk_text:
                    sub_chunks.append((cur_start, cur_start + len(cur_lines) - 1, chunk_text))
                # Carry over overlap lines if available
                overlap_lines: List[str] = []
                overlap_len = 0
                for prev in reversed(cur_lines):
                    if overlap_len + len(prev) <= self.chunk_overlap:
                        overlap_lines.insert(0, prev)
                        overlap_len += len(prev)
                    else:
                        break

                cur_start = cur_start + len(cur_lines) - len(overlap_lines)
                cur_lines = list(overlap_lines)
                cur_len = sum(len(l) + 1 for l in cur_lines)

            cur_lines.append(line)
            cur_len += line_len

        if cur_lines:
            chunk_text = "\n".join(cur_lines).strip()
            if chunk_text:
                sub_chunks.append((cur_start, end_line_1idx, chunk_text))

        return sub_chunks
