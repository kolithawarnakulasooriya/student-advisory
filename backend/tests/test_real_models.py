"""Opt-in actual Ollama/ONNX + PostgreSQL acceptance. Never falls back to a mock."""

import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.advising_worker import process_once
from app.db import context
from app.inference import ModelAdapter
from app.retrieval import candidates, reranked
from app.security import COOKIE, digest
from app.seed import fixture_id
from tests.conftest import login
from tests.test_advising import ask, complete_profile, conversation, messages, publish_source
from tests.test_intake import MID
from tests.test_staff import mutate

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MODEL_TESTS") != "1", reason="Requires pinned real local inference profile"
)


def test_real_ollama_journey(client, seeded, settings, tmp_path):
    settings.inference_provider = "ollama"
    settings.inference_gateway_token = SecretStr(
        (settings.inference_artifact_path / "gateway-token").read_text().strip()
    )
    settings.rag_database_url = SecretStr(
        "postgresql+psycopg://advisory_rag:local-rag-only@127.0.0.1:5432/advisory_test"
    )
    settings.private_storage_path = tmp_path / "private"
    adapter = ModelAdapter(settings)
    assert not adapter.mock
    complete_profile(client)
    started = time.perf_counter()
    fixture_path = Path(__file__).resolve().parents[2] / "evals/retrieval-v1.json"
    fixture = json.loads(fixture_path.read_text())
    by_id = {}
    source = None
    for doc in fixture["documents"]:
        extra = {}
        if doc.get("private_other_student"):
            extra = {
                "uploader": "multi-role",
                "target_override": {
                    "visibility": "student",
                    "org_unit_id": str(fixture_id("department-b")),
                    "student_membership_id": str(fixture_id("grant:student-b:department-b")),
                },
            }
        row, _ = publish_source(
            client,
            seeded,
            settings,
            content=doc["text"],
            **extra,
            metadata={
                "title": doc["label"],
                "program": doc["program"],
                "catalog_start": doc["catalog"],
                "catalog_end": doc["catalog"],
            },
        )
        by_id[row["id"]] = doc["label"]
        if doc["expected_eligible"]:
            source = row
    assert source
    indexing = time.perf_counter() - started
    login(client)
    retrieval_results = []
    for query in fixture["queries"]:
        vector = adapter.embed([query["question"]], query=True)[0]
        with Session(client.app.state.engine) as db, db.begin():
            context(
                db,
                user_id=str(fixture_id("student-a")),
                mfa="false",
                session_hash=digest(client.cookies.get(COOKIE)),
            )
            rows = candidates(db, MID, query["question"], vector)
        assert all(by_id[str(r["source_id"])] == "catalog-2026" for r in rows)
        ranked = reranked(adapter, query["question"], rows)
        labels = [by_id[str(r["source_id"])] for r in ranked]
        admitted = [by_id[str(r["source_id"])] for r in ranked if r["rerank_score"] >= -8]
        relevant = query["relevant"]
        if relevant:
            assert relevant in labels
        else:
            assert not admitted
        retrieval_results.append(
            {
                "question": query["question"],
                "labels": labels,
                "scores": [round(r["rerank_score"], 4) for r in ranked],
                "recall_at_10": int(relevant in labels) if relevant else None,
                "reciprocal_rank": 1 / (labels.index(relevant) + 1) if relevant in labels else None,
                "admitted": admitted,
            }
        )
    c = conversation(client)
    results = []
    for label, question in [
        ("cited", "What must I complete before enrolling in SYN102?"),
        ("unsupported", "What is the approved exception to waive all prerequisites?"),
        ("unrelated", "What is the university tuition refund policy?"),
    ]:
        login(client)
        r = ask(client, c, question)
        assert r.status_code == 201, r.text
        started = time.perf_counter()
        assert process_once(settings) == 1
        elapsed = time.perf_counter() - started
        m = max(messages(client, c), key=lambda m: m["created_at"])
        assert m["answers"], m
        answer = m["answers"][-1]
        results.append(
            {
                "label": label,
                "seconds": round(elapsed, 3),
                "disposition": answer["disposition"],
                "evidence_ids": [q["id"] for q in answer["payload"]["citations"]],
            }
        )
        if label == "cited":
            assert answer["disposition"] == "answered", answer
            assert answer["payload"]["citations"][0]["source_id"] == source["id"]
        else:
            assert answer["disposition"] == "needs_advisor", answer
    login(client, "advisor-a", True)
    version = client.get("/api/v1/conversations/" + c["id"]).json()["version"]
    response = mutate(
        client,
        "POST",
        f"conversations/{c['id']}/guidance",
        {"text": "Prefer a three course term.", "preferences": {"max_courses": 3}},
        version=version,
    )
    assert response.status_code == 201, response.text
    login(client)
    ask(client, c, "Which prerequisite applies to SYN102 for my next term?")
    started = time.perf_counter()
    process_once(settings)
    elapsed = time.perf_counter() - started
    answer = max(messages(client, c), key=lambda m: m["created_at"])["answers"][-1]
    assert answer["disposition"] == "answered", answer
    assert answer["payload"]["guidance"][0]["preferences"]["max_courses"] == 3
    results.append(
        {
            "label": "guidance_followup",
            "seconds": round(elapsed, 3),
            "disposition": answer["disposition"],
        }
    )
    r = mutate(
        client,
        "POST",
        "cases",
        {
            "student_membership_id": str(MID),
            "conversation_id": c["id"],
            "reason": "Human review of a synthetic prerequisite exception",
        },
    )
    assert r.status_code == 201, r.text
    assert client.get("/api/v1/cases/" + r.json()["id"]).json()["status"] == "open"
    report = {
        "retrieval": retrieval_results,
        "dataset_hash": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "scope_leakage": 0,
        "provider": "ollama",
        "fingerprint": adapter.fingerprint,
        "indexing_seconds": round(indexing, 3),
        "generation": results,
        "durable_case": True,
        "synthetic_only": True,
    }
    path = Path(
        os.getenv(
            "MODEL_REPORT_PATH",
            str(Path(__file__).resolve().parents[2] / "local-data/real-model-report.json"),
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
