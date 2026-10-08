"""
Text Normalization Module — Member 2 (RAG + Rules)

Performs deterministic text normalization for documents, source code,
and conversations before chunking and embedding.
Preserves indentation, code structures, markdown headings, and code fences
while removing noisy line-endings and trailing whitespace.
"""

import unicodedata


def normalize_text(text: str) -> str:
    """
    Normalizes input text deterministically:
    1. Normalizes unicode representation (Unicode NFC).
    2. Converts Windows (\r\n) and legacy Mac (\r) line endings to Unix (\n).
    3. Strips trailing whitespace per line while preserving all leading indentation.
    4. Trims excessive trailing empty lines at document end (preserves single trailing \n).
    5. Returns empty string cleanly for empty or whitespace-only inputs.
    """
    if not text:
        return ""

    # 1. Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", text)

    # 2. Line ending normalization
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Strip trailing whitespace per line without destroying leading indentation
    lines = [line.rstrip() for line in normalized.split("\n")]

    # 4. Collapse trailing empty lines at document end
    while lines and lines[-1] == "":
        lines.pop()

    if not lines:
        return ""

    # Join back with standard newline
    result = "\n".join(lines)
    return result + "\n"
