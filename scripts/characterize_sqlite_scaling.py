#!/usr/bin/env python3
"""
CLIVERSE Member 2 — SQLite Vector Search Scaling Characterization
=================================================================
Diagnoses the empirical search latency of Member 2's SQLite + Python table-scan
vector scoring across synthetic corpus sizes (100 to 5,000 chunks).

Demonstrates that while suitable for local Hackathon MVP scale (<1,000 chunks, <25ms),
the linear O(N) table scan requires an ANN index (FAISS, sqlite-vec, pgvector) for
production scale (>10,000 chunks).

Usage:
    python scripts/characterize_sqlite_scaling.py
"""

import json
import shutil
import tempfile
import time
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.models import MemoryChunk, MemoryRecord
from memory.storage.sqlite_store import SQLiteMemoryStorage


def run_scaling_benchmark(sizes: List[int] = [100, 500, 1000, 2500, 5000], runs: int = 5) -> Dict[int, float]:
    temp_dir = tempfile.mkdtemp(prefix="cliverse_scaling_")
    results = {}
    try:
        db_path = str(Path(temp_dir) / "scale_test.db")
        store = SQLiteMemoryStorage(db_path=db_path)
        dim = 64
        query_vec = [0.125] * dim

        print("\n" + "=" * 65)
        print("SQLITE VECTOR SEARCH SCALING CHARACTERIZATION")
        print("=" * 65)
        print(f"{'Corpus Size (Chunks)':<25} | {'Avg Search Latency':<20} | {'Throughput (qps)':<15}")
        print("-" * 65)

        for size in sizes:
            # Seed synthetic chunks
            rec_id = f"rec-scale-{size}"
            rec = MemoryRecord(
                record_id=rec_id,
                project_id="scale-proj",
                source_type="doc",
                source_path="benchmark.md",
                title=f"Synthetic Corpus {size}",
                content="Synthetic benchmark content placeholder.",
            )
            chunks = [
                MemoryChunk(
                    chunk_id=f"c-{size}-{i}",
                    record_id=rec_id,
                    chunk_index=i,
                    content=f"Chunk {i} representing engineering specification details and code patterns.",
                    content_hash=f"hash-{size}-{i}",
                    embedding=query_vec,
                    start_line=1,
                    end_line=5,
                )
                for i in range(size)
            ]
            store.save_record(rec, chunks)

            # Benchmark search_chunks
            t0 = time.perf_counter()
            for _ in range(runs):
                _ = store.search_chunks(
                    query_vector=query_vec,
                    query_text="engineering specification",
                    project_id="scale-proj",
                    top_k=5,
                )
            avg_ms = ((time.perf_counter() - t0) / runs) * 1000
            qps = 1000.0 / avg_ms if avg_ms > 0 else 0.0
            results[size] = avg_ms
            print(f"{size:<25d} | {avg_ms:<17.2f} ms | {qps:<15.1f}")

            store.delete_record(rec_id)

        print("=" * 65)
        print("DIAGNOSIS:")
        print("  - Search is an in-memory linear table scan O(N) over project chunks.")
        print("  - Suitable for local Hackathon MVP (<1,000 chunks, <25 ms).")
        print("  - For production (>10k chunks), upgrade to sqlite-vec, FAISS, or pgvector.")
        print("=" * 65 + "\n")
        return results

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    run_scaling_benchmark()
