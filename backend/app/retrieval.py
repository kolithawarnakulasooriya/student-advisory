"""Authorization and applicability are applied before either candidate LIMIT."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inference import ModelAdapter

ELIGIBLE = """WITH eligible AS MATERIALIZED (
 SELECT e.id,e.text,e.embedding,e.locator,e.source_version_id,v.source_id,v.metadata_fields,
 p.published_at FROM evidence_chunks e JOIN index_builds b ON b.id=e.build_id
 JOIN source_versions v ON v.id=e.source_version_id JOIN source_publications p ON p.build_id=b.id
 JOIN sources s ON s.id=v.source_id JOIN knowledge_states k ON k.id=s.institution_id
 WHERE b.state='ready' AND k.config_id=b.config_id AND p.status='published'
 AND rag_published(v.id,:mid,true)
) """


def candidates(db: Session, mid: UUID, question: str, vector: list[float]) -> list[dict[str, Any]]:
    # Exact filtered vector search avoids ANN over-fetch/post-filter privacy mistakes.
    vector_rows = (
        db.execute(
            text(
                ELIGIBLE
                + """SELECT * FROM eligible
 ORDER BY embedding <=> CAST(:embedding AS vector),id LIMIT 20"""
            ),
            {"mid": mid, "embedding": json.dumps(vector)},
        )
        .mappings()
        .all()
    )
    keyword_rows = (
        db.execute(
            text(
                ELIGIBLE
                + """SELECT * FROM eligible
 WHERE to_tsvector('english',text) @@ plainto_tsquery('english',:question)
 ORDER BY ts_rank_cd(to_tsvector('english',text),
 plainto_tsquery('english',:question)) DESC,id LIMIT 20"""
            ),
            {"mid": mid, "question": question},
        )
        .mappings()
        .all()
    )
    scores: dict[str, float] = {}
    rows: dict[str, dict[str, Any]] = {}
    for channel in (vector_rows, keyword_rows):
        for rank, row in enumerate(channel, 1):
            key = str(row["id"])
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
            # Do not carry vectors into model requests or traces.
            rows[key] = {k: v for k, v in row.items() if k != "embedding"}
    return [rows[key] for key in sorted(scores, key=lambda k: (-scores[k], k))[:30]]


def reranked(
    adapter: ModelAdapter, question: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not rows:
        return []
    scores = adapter.rerank(question, [row["text"] for row in rows])
    return [
        {**row, "rerank_score": score}
        for score, row in sorted(
            zip(scores, rows, strict=True), key=lambda item: (-item[0], str(item[1]["id"]))
        )[:10]
    ]


def citation_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "source_id": str(row["source_id"]),
        "source_version_id": str(row["source_version_id"]),
        "title": row["metadata_fields"]["title"],
        "quote": row["text"],
        "locator": row["locator"],
        "status": "published",
        "published_at": row["published_at"].isoformat(),
    }


def selection_valid(value: Any, evidence: list[dict[str, Any]]) -> bool:
    if not isinstance(value, dict) or set(value) != {"disposition", "evidence_ids", "reason_code"}:
        return False
    if not isinstance(value["disposition"], str) or value["disposition"] not in {
        "answered",
        "needs_clarification",
        "needs_advisor",
    }:
        return False
    if not isinstance(value["reason_code"], str) or value["reason_code"] not in {
        "evidence",
        "missing_fact",
        "no_support",
        "policy_conflict",
    }:
        return False
    ids = value["evidence_ids"]
    permitted = {e["id"] for e in evidence}
    return (
        isinstance(ids, list)
        and len(ids) <= 4
        and all(isinstance(i, str) for i in ids)
        and len(set(ids)) == len(ids)
        and set(ids) <= permitted
        and (value["disposition"] != "answered" or bool(ids))
    )
