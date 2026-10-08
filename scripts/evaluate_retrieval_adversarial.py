#!/usr/bin/env python3
"""
CLIVERSE Member 2 — Adversarial RAG Retrieval Evaluation Script
===============================================================
P0-5: Adversarial RAG Validation & Diagnosis

Loads the adversarial evaluation dataset from tests/fixtures/retrieval_eval_adversarial.json,
ingests documents into a temporary SQLite database, runs 20 challenging adversarial queries,
and calculates:
  - Recall@1, Recall@3, Recall@5
  - Precision@1, Precision@3, Precision@5
  - MRR (Mean Reciprocal Rank)
  - Failure attribution:
      * no relevant candidate retrieved
      * relevant candidate retrieved but below threshold
      * relevant candidate removed by deduplication
      * relevant candidate ranked below top-K

Usage:
    python scripts/evaluate_retrieval_adversarial.py
    python scripts/evaluate_retrieval_adversarial.py --top-k 5 --min-score 0.1
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path so we can import from memory/
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.embeddings.local_engine import LocalBaselineEmbeddingProvider
from memory.ingestion.pipeline import IngestionPipeline
from memory.retrieval.ranking import rank_and_deduplicate_results
from memory.retrieval.search import RetrievalService
from memory.storage.sqlite_store import SQLiteMemoryStorage


# ── Metrics Helpers ──────────────────────────────────────────────────────────

def recall_at_k(results: list, expected_sources: List[str], k: int) -> float:
    """Recall@K: fraction of expected sources found in top-k results (for positive queries)."""
    if not expected_sources:
        return 0.0
    top_k_paths = {r.source_path for r in results[:k]}
    found = sum(1 for s in expected_sources if s in top_k_paths)
    return found / len(expected_sources)


def precision_at_k(results: list, expected_sources: List[str], k: int) -> float:
    """Precision@K: fraction of top-k results that are relevant (for positive queries)."""
    if not expected_sources or not results or k == 0:
        return 0.0
    top_k = results[:k]
    relevant = sum(1 for r in top_k if r.source_path in expected_sources)
    return relevant / min(k, len(top_k))


def reciprocal_rank(results: list, expected_sources: List[str]) -> float:
    """Reciprocal Rank for MRR calculation on positive queries (0.0 if not found)."""
    if not expected_sources:
        return 0.0
    for i, r in enumerate(results, start=1):
        if r.source_path in expected_sources:
            return 1.0 / i
    return 0.0


# ── Failure Attribution Classifier ───────────────────────────────────────────

def attribute_failure(
    query: str,
    expected_sources: List[str],
    results: list,
    storage: SQLiteMemoryStorage,
    embedding_provider: LocalBaselineEmbeddingProvider,
    project_id: str,
    top_k: int = 5,
    min_score: float = 0.1,
) -> str:
    """
    Attributes failure into explicit causal categories:
      - no relevant candidate retrieved
      - relevant candidate retrieved but below threshold
      - relevant candidate removed by deduplication
      - relevant candidate ranked below top-K
      - false positive candidates retrieved (for negative queries)
    """
    if not expected_sources:
        if results:
            return "false positive candidates retrieved"
        return "correct negative rejection"

    top_k_paths = {r.source_path for r in results[:top_k]}
    if any(s in top_k_paths for s in expected_sources):
        return "success"

    # Query storage directly at min_score=0.0 to inspect raw candidate pool
    query_vec = embedding_provider.embed_query(query)
    raw_candidates = storage.search_chunks(
        query_vector=query_vec,
        query_text=query,
        top_k=100,
        project_id=project_id,
        min_score=0.0,
    )
    matching_raw = [c for c in raw_candidates if c.source_path in expected_sources]

    if not matching_raw:
        return "no relevant candidate retrieved"

    above_threshold = [c for c in matching_raw if c.score >= min_score]
    if not above_threshold:
        return "relevant candidate retrieved but below threshold"

    deduped = rank_and_deduplicate_results(raw_candidates, min_score=min_score, top_k=100)
    deduped_paths = {d.source_path for d in deduped}
    if not any(s in deduped_paths for s in expected_sources):
        return "relevant candidate removed by deduplication"

    return "relevant candidate ranked below top-K"


# ── Main Evaluator ────────────────────────────────────────────────────────────

def run_adversarial_evaluation(
    fixture_path: Optional[str] = None,
    top_k: int = 5,
    min_score: float = 0.1,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Executes adversarial retrieval evaluation against tests/fixtures/retrieval_eval_adversarial.json.
    """
    if fixture_path is None:
        fixture_path = str(
            Path(__file__).parent.parent / "tests" / "fixtures" / "retrieval_eval_adversarial.json"
        )

    with open(fixture_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    documents = dataset["documents"]
    queries = dataset["queries"]
    default_project_id = dataset.get("project_id", "cliverse-eval")

    temp_dir = tempfile.mkdtemp(prefix="cliverse_adv_eval_")
    db_path = Path(temp_dir) / "adv_eval.db"

    try:
        storage = SQLiteMemoryStorage(db_path=str(db_path))
        embedding_provider = LocalBaselineEmbeddingProvider(dimension=64)
        ingestion = IngestionPipeline(
            storage=storage,
            embedding_provider=embedding_provider,
        )
        retrieval = RetrievalService(
            storage=storage,
            embedding_provider=embedding_provider,
        )

        for doc in documents:
            ingestion.ingest(
                content=doc["content"],
                project_id=default_project_id,
                source_type=doc["source_type"],
                source_path=doc["source_path"],
                title=doc["title"],
            )

        all_results = {}
        pos_queries = [q for q in queries if q.get("expected_sources")]
        neg_queries = [q for q in queries if not q.get("expected_sources")]

        all_results = {}
        pos_recall_scores = {1: [], 3: [], 5: []}
        pos_precision_scores = {1: [], 3: [], 5: []}
        pos_rr_scores = []
        pos_successes = []
        pos_failures = []
        attributions: Dict[str, int] = {}
        successes = []
        failures = []

        # ── 1. Evaluate Positive Queries ──────────────────────────────────────
        for q in pos_queries:
            qid = q["id"]
            query_text = q["query"]
            expected = q["expected_sources"]
            proj_id = q.get("project_override", default_project_id)

            results = retrieval.search_memory(
                query=query_text,
                project_id=proj_id,
                top_k=top_k,
                min_score=min_score,
            )
            all_results[qid] = results

            for k_val in [1, 3, 5]:
                pos_recall_scores[k_val].append(recall_at_k(results, expected, k_val))
                pos_precision_scores[k_val].append(precision_at_k(results, expected, k_val))

            rr = reciprocal_rank(results, expected)
            pos_rr_scores.append(rr)

            attr = attribute_failure(
                query=query_text,
                expected_sources=expected,
                results=results,
                storage=storage,
                embedding_provider=embedding_provider,
                project_id=proj_id,
                top_k=top_k,
                min_score=min_score,
            )

            entry = {"query": q, "results": results, "attribution": attr}
            if attr == "success":
                pos_successes.append(entry)
                successes.append(entry)
            else:
                pos_failures.append(entry)
                failures.append(entry)
                attributions[attr] = attributions.get(attr, 0) + 1

        # ── 2. Evaluate Negative / Irrelevant Queries ─────────────────────────
        neg_true_negatives = []
        neg_false_positives = []
        neg_retrieved_counts = []

        for q in neg_queries:
            qid = q["id"]
            query_text = q["query"]
            expected = q.get("expected_sources", [])
            proj_id = q.get("project_override", default_project_id)

            results = retrieval.search_memory(
                query=query_text,
                project_id=proj_id,
                top_k=top_k,
                min_score=min_score,
            )
            all_results[qid] = results
            neg_retrieved_counts.append(len(results))

            attr = attribute_failure(
                query=query_text,
                expected_sources=expected,
                results=results,
                storage=storage,
                embedding_provider=embedding_provider,
                project_id=proj_id,
                top_k=top_k,
                min_score=min_score,
            )

            entry = {"query": q, "results": results, "attribution": attr}
            if not results:
                neg_true_negatives.append(entry)
                successes.append(entry)
            else:
                neg_false_positives.append(entry)
                failures.append(entry)
                attributions[attr] = attributions.get(attr, 0) + 1

        n_pos = len(pos_queries)
        n_neg = len(neg_queries)
        n_total = len(queries)

        pos_r1 = sum(pos_recall_scores[1]) / n_pos if n_pos else 0.0
        pos_r3 = sum(pos_recall_scores[3]) / n_pos if n_pos else 0.0
        pos_r5 = sum(pos_recall_scores[5]) / n_pos if n_pos else 0.0
        pos_p1 = sum(pos_precision_scores[1]) / n_pos if n_pos else 0.0
        pos_p3 = sum(pos_precision_scores[3]) / n_pos if n_pos else 0.0
        pos_p5 = sum(pos_precision_scores[5]) / n_pos if n_pos else 0.0
        pos_mrr = sum(pos_rr_scores) / n_pos if n_pos else 0.0

        metrics = {
            "total_queries": n_total,
            "positive_queries": n_pos,
            "negative_queries": n_neg,
            "overall_success_count": len(successes),
            "overall_failure_count": len(failures),
            # Positive queries unpolluted
            "pos_recall_1": pos_r1,
            "pos_recall_3": pos_r3,
            "pos_recall_5": pos_r5,
            "pos_precision_1": pos_p1,
            "pos_precision_3": pos_p3,
            "pos_precision_5": pos_p5,
            "pos_mrr": pos_mrr,
            "pos_success_count": len(pos_successes),
            "pos_failure_count": len(pos_failures),
            # Negative queries
            "neg_true_negatives": len(neg_true_negatives),
            "neg_false_positives": len(neg_false_positives),
            "neg_rejection_rate": len(neg_true_negatives) / n_neg if n_neg else 0.0,
            "neg_false_positive_rate": len(neg_false_positives) / n_neg if n_neg else 0.0,
            "neg_avg_retrieved_above_threshold": sum(neg_retrieved_counts) / n_neg if n_neg else 0.0,
            # Aliases for compatibility
            "recall_1": pos_r1,
            "recall_3": pos_r3,
            "recall_5": pos_r5,
            "precision_1": pos_p1,
            "precision_3": pos_p3,
            "precision_5": pos_p5,
            "mrr": pos_mrr,
            "success_count": len(successes),
            "failure_count": len(failures),
            "attributions": attributions,
            "failures": failures,
            "successes": successes,
        }

        if verbose:
            print("\n" + "=" * 60)
            print("ADVERSARIAL RAG RETRIEVAL EVALUATION REPORT")
            print("=" * 60)
            print(f"Total adversarial queries: {n_total}")
            print(f"  * Positive queries     : {n_pos}")
            print(f"  * Negative queries     : {n_neg}")
            print(f"Overall Succeeded (@5)   : {metrics['overall_success_count']}/{n_total}")
            print(f"Overall Failed    (@5)   : {metrics['overall_failure_count']}/{n_total}")
            print("-" * 60)
            print("POSITIVE QUERY METRICS (Unpolluted by Negatives):")
            print(f"  Recall@1               : {pos_r1:.1%}")
            print(f"  Recall@3               : {pos_r3:.1%}")
            print(f"  Recall@5               : {pos_r5:.1%}")
            print(f"  Precision@1            : {pos_p1:.1%}")
            print(f"  Precision@3            : {pos_p3:.1%}")
            print(f"  Precision@5            : {pos_p5:.1%}")
            print(f"  MRR                    : {pos_mrr:.3f}")
            print(f"  Positive Succeeded (@5): {metrics['pos_success_count']}/{n_pos}")
            print(f"  Positive Failed    (@5): {metrics['pos_failure_count']}/{n_pos}")
            print("-" * 60)
            print("NEGATIVE QUERY BEHAVIOR (Out-of-Domain Rejection):")
            print(f"  True Negatives (Clean) : {metrics['neg_true_negatives']}/{n_neg}")
            print(f"  False Positives        : {metrics['neg_false_positives']}/{n_neg}")
            print(f"  Rejection Rate         : {metrics['neg_rejection_rate']:.1%}")
            print(f"  False-Positive Rate    : {metrics['neg_false_positive_rate']:.1%}")
            print(f"  Avg Retrieved Above Min: {metrics['neg_avg_retrieved_above_threshold']:.2f}")
            print("-" * 60)
            print("FAILURE ATTRIBUTION BREAKDOWN:")
            for reason, count in sorted(attributions.items(), key=lambda x: -x[1]):
                print(f"  * {reason:<50}: {count} queries")
            print("=" * 60)

        return metrics

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run adversarial RAG evaluation")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K cutoff (default: 5)")
    parser.add_argument("--min-score", type=float, default=0.1, help="Min score threshold (default: 0.1)")
    args = parser.parse_args()

    run_adversarial_evaluation(top_k=args.top_k, min_score=args.min_score, verbose=True)
