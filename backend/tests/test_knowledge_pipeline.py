from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select


@pytest.fixture
def pipeline(client, monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.core.database import session_factory
    from app.models import Product, ProductVersion, User
    from app.services import ingestion, knowledge, vectorstore

    get_settings().chroma_dir = tmp_path / "vectors"
    monkeypatch.setattr(vectorstore, "_client", None)
    monkeypatch.setattr(vectorstore, "_ENSURED", False)
    embedder = SimpleNamespace(
        embed_documents=lambda texts: [[1.0, 0.0] for _ in texts], embed_query=lambda text: [1.0, 0.0]
    )
    monkeypatch.setattr(vectorstore, "get_embedding_service", lambda: embedder)
    monkeypatch.setattr(ingestion, "get_embedding_service", lambda: embedder)
    with session_factory()() as db, db.begin():
        admin = db.scalar(select(User).where(User.username == "admin"))
        product = Product(name="Atlas", description="test")
        db.add(product)
        db.flush()
        versions = [ProductVersion(product_id=product.id, name=n) for n in ["2.0", "3.0"]]
        db.add_all(versions)
    return SimpleNamespace(
        knowledge=knowledge,
        ingestion=ingestion,
        vectorstore=vectorstore,
        admin=admin.id,
        product=product.id,
        v1=versions[0].id,
        v2=versions[1].id,
    )


def upload(p, content=b"old policy", version=None):
    return p.knowledge.enqueue("manual.txt", content, p.admin, p.product, version or p.v1)


def publish(p, result):
    history = p.knowledge.history(result["document_id"])
    return p.knowledge.change(
        result["document_id"], "publish", p.admin, history["revision"], result["revision_id"]
    )


def test_async_upload_dedup_and_original_rbac(pipeline, client, login):
    p = pipeline
    login("staff")
    response = client.post(
        "/api/documents/upload",
        data={"product_id": p.product, "version_id": p.v1},
        files={"files": ("manual.txt", b"original policy")},
    )
    assert response.status_code == 202
    row = response.json()["results"][0]
    assert row["revision"]["state"] == "queued" and row["revision"]["job"]["attempts"] == 0
    assert p.vectorstore.get_collection().count() == 0
    again = upload(p, b"original policy")
    assert again["deduplicated"] and again["revision_id"] == row["revision_id"]
    url = f"/api/documents/{row['document_id']}/revisions/{row['revision_id']}/original"
    assert client.get(url).content == b"original policy"
    assert (
        client.post(
            f"/api/documents/{row['document_id']}/publish",
            json={"revision": 1, "revision_id": row["revision_id"]},
        ).status_code
        == 403
    )
    login()
    assert client.get(url).status_code == 403
    assert client.get("/api/documents/jobs").status_code == 403
    assert client.get(f"/api/documents/{row['document_id']}/revisions").status_code == 403
    assert client.get("/api/documents").json() == []
    assert (
        client.get(
            f"/api/documents/{row['document_id']}/chunks", params={"revision_id": row["revision_id"]}
        ).status_code
        == 404
    )


def test_publish_isolation_failed_new_revision_and_rollback(pipeline):
    p = pipeline
    old = upload(p)
    assert p.ingestion.run_once()
    assert p.knowledge.search("q") == []
    publish(p, old)
    assert p.knowledge.search("q")[0]["content"] == "old policy"
    new = upload(p, b"new policy")
    with pytest.raises(HTTPException) as early:
        publish(p, new)
    assert early.value.status_code == 409
    p.ingestion.run_once()
    assert p.knowledge.search("q")[0]["revision_id"] == old["revision_id"]
    changed = publish(p, new)
    assert [h["content"] for h in p.knowledge.search("q")] == ["new policy"]
    with pytest.raises(HTTPException) as stale:
        p.knowledge.change(new["document_id"], "withdraw", p.admin, changed["revision"] - 1)
    assert stale.value.status_code == 409
    publish(p, old)
    assert [h["content"] for h in p.knowledge.search("q")] == ["old policy"]
    failed = upload(p, b"bad pending policy")
    lease = p.ingestion.claim()
    p.ingestion.finish(*lease, error="synthetic parse error")
    assert p.knowledge.search("q")[0]["revision_id"] == old["revision_id"]
    assert failed["revision_id"] not in p.knowledge.eligible_revisions()


def test_same_filename_scopes_and_inactive_filter(pipeline):
    p = pipeline
    a, b = upload(p, b"v2", p.v1), upload(p, b"v3", p.v2)
    for result in [a, b]:
        p.ingestion.run_once()
        publish(p, result)
    assert a["document_id"] != b["document_id"]
    assert p.knowledge.search("q", product_id=p.product, version_id=p.v2)[0]["content"] == "v3"
    with pytest.raises(HTTPException) as ambiguous:
        p.knowledge.history("manual.txt")
    assert ambiguous.value.status_code == 409
    from app.core.database import session_factory
    from app.models import ProductVersion

    with session_factory()() as db, db.begin():
        db.get(ProductVersion, p.v2).is_active = False
    assert len(p.knowledge.documents()) == 1
    assert p.knowledge.search("q", product_id=p.product, version_id=p.v2) == []
    assert len(p.knowledge.documents(staff=True)) == 2


def test_withdraw_scope_archive_restore(pipeline):
    p = pipeline
    row = upload(p)
    p.ingestion.run_once()
    pub = publish(p, row)
    with pytest.raises(HTTPException):
        p.knowledge.change(
            row["document_id"], "scope", p.admin, pub["revision"], product_id=p.product, version_id=p.v2
        )
    withdrawn = p.knowledge.change(row["document_id"], "withdraw", p.admin, pub["revision"])
    assert p.knowledge.search("q") == []
    p.knowledge.change(
        row["document_id"], "scope", p.admin, withdrawn["revision"], product_id=p.product, version_id=p.v2
    )
    pub = publish(p, row)
    assert p.knowledge.search("q", version_id=p.v1) == []
    assert len(p.knowledge.search("q", version_id=p.v2)) == 1
    archived = p.knowledge.change(row["document_id"], "archive", p.admin, pub["revision"])
    assert p.knowledge.search("q") == []
    with pytest.raises(HTTPException):
        publish(p, row)
    p.knowledge.change(row["document_id"], "restore", p.admin, archived["revision"])
    assert p.knowledge.search("q") == []
    publish(p, row)
    actions = [e["action"] for e in p.knowledge.history(row["document_id"])["events"]]
    assert {"upload", "index_ready", "publish", "withdraw", "scope", "archive", "restore"} <= set(actions)


def test_job_exclusive_claim_restart_fencing_and_retry(pipeline):
    p = pipeline
    row = upload(p)
    with ThreadPoolExecutor(max_workers=4) as pool:
        leases = list(pool.map(lambda _: p.ingestion.claim(), range(4)))
    leases = [lease for lease in leases if lease]
    assert len(leases) == 1
    old_lease = leases[0]
    assert p.ingestion.renew(*old_lease)
    from app.core.database import session_factory
    from app.models import IngestionJob, utcnow

    with session_factory()() as db, db.begin():
        job = db.get(IngestionJob, old_lease[0])
        job.lease_until = utcnow() - timedelta(seconds=1)
    assert not p.ingestion.finish(*old_lease, count=1)
    new_lease = p.ingestion.claim()
    assert new_lease[1] != old_lease[1]
    assert not p.ingestion.renew(*old_lease)
    assert not p.ingestion.finish(*old_lease, count=99)
    p.ingestion.finish(*new_lease, error="temporary error")
    assert p.ingestion.claim() is None  # backoff
    with session_factory()() as db, db.begin():
        job = db.get(IngestionJob, new_lease[0])
        job.available_at = utcnow() - timedelta(seconds=1)
    third = p.ingestion.claim()
    p.ingestion.finish(*third, error="still failing")
    history = p.knowledge.history(row["document_id"])
    assert history["revisions"][0]["state"] == "failed"
    retried = p.knowledge.retry_job(third[0], p.admin)
    assert retried["attempts"] == 3 and retried["max_attempts"] == 6
    assert p.ingestion.run_once()
    assert p.knowledge.history(row["document_id"])["revisions"][0]["state"] == "ready"
    assert p.vectorstore.get_collection().count() == 1


def test_partial_vector_write_retries_idempotently(pipeline, monkeypatch):
    p = pipeline
    row = upload(p, b"alpha " * 400)
    real_upsert = p.ingestion.upsert_revision
    calls = []

    def partial(doc, rev, number, name, chunks, vectors):
        real_upsert(doc, rev, number, name, chunks[:1], vectors[:1])
        calls.append(1)
        raise RuntimeError("private-service-address-secret")

    monkeypatch.setattr(p.ingestion, "upsert_revision", partial)
    p.ingestion.run_once()
    history = p.knowledge.history(row["document_id"])
    job = history["revisions"][0]["job"]
    assert "private-service" not in job["error"] and p.knowledge.search("q") == []
    from app.core.database import session_factory
    from app.models import IngestionJob, utcnow

    with session_factory()() as db, db.begin():
        db.get(IngestionJob, job["id"]).available_at = utcnow() - timedelta(seconds=1)
    monkeypatch.setattr(p.ingestion, "upsert_revision", real_upsert)
    p.ingestion.run_once()
    ready = p.knowledge.history(row["document_id"])["revisions"][0]
    assert ready["state"] == "ready" and ready["chunks"] > 1
    assert p.vectorstore.get_collection().count() == ready["chunks"]


def test_checksum_failure_and_worker_status(pipeline):
    p = pipeline
    row = upload(p)
    from app.core.config import get_settings
    from app.core.database import session_factory
    from app.models import IngestionJob

    (get_settings().document_storage_dir / (row["revision_id"] + ".bin")).write_bytes(b"tampered")
    with session_factory()() as db, db.begin():
        db.get(IngestionJob, row["revision"]["job"]["id"]).max_attempts = 1
    p.ingestion.run_once()
    assert p.knowledge.history(row["document_id"])["revisions"][0]["state"] == "failed"
    assert not p.knowledge.queue_status()["worker_online"]
    p.ingestion.heartbeat("test-worker")
    assert p.knowledge.queue_status()["worker_online"]


def test_legacy_adoption_is_repeatable_and_has_no_fake_original(pipeline):
    p = pipeline
    p.vectorstore.add_documents("legacy.txt", ["old content"])
    assert p.knowledge.search("q") == []
    assert p.knowledge.adopt_legacy() == 1
    assert p.knowledge.adopt_legacy() == 0
    row = p.knowledge.documents()[0]
    assert row["latest"]["original_available"] is False
    assert p.knowledge.search("q")[0]["revision_number"] == 1
    assert p.vectorstore.get_collection().count() == 1


def test_type_path_limits_and_embed_model_guard(pipeline, client, login):
    p = pipeline
    login("staff")
    response = client.post("/api/documents/upload", files={"files": ("bad.exe", b"payload")})
    assert response.json()["failed"] == 1
    row = p.knowledge.enqueue("../../safe.txt", b"safe", p.admin)
    assert p.knowledge.documents(staff=True)[0]["source"] == "safe.txt"
    p.ingestion.run_once()
    from app.core.config import get_settings

    get_settings().embedding_model = "changed/model"
    with pytest.raises(HTTPException) as mismatch:
        publish(p, row)
    assert mismatch.value.status_code == 409


@pytest.mark.parametrize(
    "content, expected",
    [
        ('{"query":"Atlas 3.0 E401 处理"}', "rewritten"),
        ('{"query":""}', "fallback"),
        ('{"query":42}', "fallback"),
        ("not json", "fallback"),
        ('{"query":"safe","scope":"other"}', "fallback"),
        ('{"query":"' + "a" * 513 + '"}', "fallback"),
    ],
)
def test_rewrite_json_validation_and_scope(pipeline, monkeypatch, content, expected):
    from app.services import rag

    captured = {}

    class Client:
        def with_options(self, **kwargs):
            return self

        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None
            )

        def close(self):
            captured["closed"] = True

        @property
        def chat(self):
            return SimpleNamespace(completions=self)

    monkeypatch.setattr(rag, "_build_client", lambda _: Client())
    trace = rag.rewrite_query("那怎么处理？", [{"role": "user", "content": "Atlas 3.0 E401"}])
    assert trace["status"] == expected
    if expected == "fallback":
        assert trace["query"] == "那怎么处理？"
    assert captured["closed"]
    assert len(captured["messages"][1]["content"]) < 5000


def test_rewrite_timeout_fallback_and_no_history_no_model(pipeline, monkeypatch):
    from app.services import rag

    def unavailable(_):
        raise TimeoutError("hidden-provider-secret")

    monkeypatch.setattr(rag, "_build_client", unavailable)
    assert rag.rewrite_query("q")["status"] == "not_needed"
    assert rag.rewrite_query("q", [{"role": "user", "content": "h"}])["status"] == "fallback"
    assert "secret" not in str(rag.rewrite_query("q", [{"role": "user", "content": "h"}]))


def test_rewrite_keeps_retrieval_scope_and_draft_excluded(pipeline, monkeypatch):
    p = pipeline
    from app.services import rag

    a, b = upload(p, b"version 2", p.v1), upload(p, b"version 3", p.v2)
    for row in [a, b]:
        p.ingestion.run_once()
        publish(p, row)
    upload(p, b"secret draft", p.v2)
    p.ingestion.run_once()
    monkeypatch.setattr(rag, "rewrite_query", lambda q, h: {"query": "version 2 malicious rewrite"})
    hits, _ = rag.retrieve(
        "q", history=[{"role": "user", "content": "h"}], product_id=p.product, version_id=p.v2
    )
    assert [h["content"] for h in hits] == ["version 3"]
