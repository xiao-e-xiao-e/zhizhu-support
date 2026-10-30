from types import SimpleNamespace

import pytest


def test_real_chroma_metadata_scope_and_reclassification(client, tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import vectorstore

    get_settings().chroma_dir = tmp_path / "isolated-vectors"
    monkeypatch.setattr(vectorstore, "_client", None)
    monkeypatch.setattr(vectorstore, "_ENSURED", False)
    monkeypatch.setattr(
        vectorstore,
        "get_embedding_service",
        lambda: SimpleNamespace(
            embed_documents=lambda texts: [[1.0, 0.0] for _ in texts], embed_query=lambda text: [1.0, 0.0]
        ),
    )
    vectorstore.add_documents("v1.txt", ["old"], product_id="p1", version_id="v1")
    vectorstore.add_documents("v2.txt", ["new"], product_id="p1", version_id="v2")
    vectorstore.add_documents("other.txt", ["other"], product_id="p2", version_id="v1")
    vectorstore.add_documents("legacy.txt", ["legacy"])
    with pytest.raises(ValueError, match="属于其他产品或版本"):
        vectorstore.add_documents("v1.txt", ["must not overwrite"], product_id="p1", version_id="v2")
    assert vectorstore.get_document_chunks("v1.txt")[0]["content"] == "old"
    assert {r["source"] for r in vectorstore.search("q", top_k=10, product_id="p1")} == {"v1.txt", "v2.txt"}
    assert [r["source"] for r in vectorstore.search("q", top_k=10, product_id="p1", version_id="v2")] == [
        "v2.txt"
    ]
    assert vectorstore.set_document_scope("legacy.txt", "p1", "v2") == 1
    assert {r["source"] for r in vectorstore.search("q", top_k=10, product_id="p1", version_id="v2")} == {
        "v2.txt",
        "legacy.txt",
    }
    assert vectorstore.get_collection().count() == 4
    assert vectorstore.set_document_scope("missing", None, None) == 0
