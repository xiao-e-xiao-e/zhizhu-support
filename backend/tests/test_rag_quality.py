from types import SimpleNamespace

import pytest


def test_stream_metrics_and_client_resources(client, monkeypatch):
    from app.services import rag

    closed = []
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="已验证[资料1]"))], usage=None
        ),
        SimpleNamespace(
            choices=[], usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4, total_tokens=15)
        ),
    ]

    class Stream:
        def __enter__(self):
            return iter(chunks)

        def __exit__(self, *args):
            closed.append("stream")

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append("client")

        @property
        def chat(self):
            return SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: Stream()))

    monkeypatch.setattr(rag, "_build_client", lambda _: Client())
    monkeypatch.setattr(
        rag, "search", lambda *args, **kwargs: [{"source": "published", "content": "verified"}]
    )
    events = list(rag.ask_stream("q"))
    assert [e["type"] for e in events] == ["retrieval", "contexts", "delta", "done"]
    assert events[-1]["data"]["usage"]["total_tokens"] == 15
    assert events[-1]["data"]["first_token_ms"] is not None
    assert closed == ["stream", "client"]


def test_empty_generation_raises_and_closes_client(client, monkeypatch):
    from app.services import rag

    closed = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        @property
        def chat(self):
            return SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=""))], usage=None
                    )
                )
            )

    monkeypatch.setattr(rag, "_build_client", lambda _: Client())
    monkeypatch.setattr(
        rag, "search", lambda *args, **kwargs: [{"source": "published", "content": "verified"}]
    )
    with pytest.raises(RuntimeError, match="空回答"):
        rag.ask("q")
    assert closed == [True]


def test_provider_specific_options_do_not_leak_to_other_hosts(client):
    from app.services.rag import model_options

    assert model_options({"api_base_url": "https://api.deepseek.com/v1"}) == {
        "extra_body": {"thinking": {"type": "disabled"}}
    }
    assert model_options({"api_base_url": "https://api.example.com/v1"}) == {}
