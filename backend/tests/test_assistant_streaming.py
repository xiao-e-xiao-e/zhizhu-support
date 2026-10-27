# ruff: noqa: F811
import json
from types import SimpleNamespace

import pytest
from test_workflows import execute, fake_model, model_response, new_run, workflow  # noqa: F401


def events(p, run):
    return list(p.agent.execute(p.users["alice"], run["id"]))


@pytest.mark.parametrize(
    "question,answer",
    [
        ("你好", "你好！有什么想聊的？"),
        ("谢谢你的帮助", "不客气，随时来找我。"),
        ("帮我写一句鼓励自己的话", "今天的一小步，也值得为自己鼓掌。🙂"),
    ],
)
def test_general_chat_streams_before_completion_without_knowledge(
    workflow, client, login, monkeypatch, question, answer
):
    captured, _ = fake_model(monkeypatch, [model_response("general_chat"), model_response(answer=answer)])
    login()
    run = new_run(client, question=question)
    iterator = workflow.agent.execute(workflow.users["alice"], run["id"])
    pieces = []
    for event in iterator:
        if event["type"] == "answer_delta":
            delta = event["data"]
            assert delta["offset"] == len("".join(pieces).encode("utf-16-le")) // 2
            pieces.append(delta["text"])
            # The generator is paused before completion: the first text is already persisted.
            assert workflow.agent.get_run(workflow.users["alice"], run["id"])["status"] == "running"
    assert len(pieces) > 1 and "".join(pieces) == answer
    final = workflow.agent.get_run(workflow.users["alice"], run["id"])
    assert final["status"] == "completed" and not final["result"].get("needs_input")
    assert final["result"]["answer"] == answer and final["result"]["contexts"] == []
    assert captured[1]["stream"] is True
    assert client.get("/api/sessions/" + run["session"]).json()["messages"][-1]["content"] == answer


def test_identity_reads_only_allowlisted_runtime_information(workflow, client, login, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    settings.chat_model = "team-configured-model"
    settings.api_key = "secret-not-for-users"
    settings.api_base_url = "https://private-provider.example/v1"
    captured, _ = fake_model(
        monkeypatch,
        [
            model_response("get_assistant_info"),
            model_response(answer="我是智能客服助手，当前应用配置的模型是 team-configured-model。"),
        ],
    )
    login()
    output = events(workflow, new_run(client, question="你的大模型是什么？"))
    final = output[-1]["data"]
    assert not final["result"].get("needs_input")
    assert final["result"]["assistant_info"]["configured_model"] == "team-configured-model"
    assert "secret-not-for-users" not in json.dumps(output)
    assert "private-provider" not in json.dumps(output)
    assert captured[1]["stream"] and "team-configured-model" in captured[1]["messages"][-1]["content"]


def test_fragmented_stream_tool_calls_still_use_validated_tools(workflow, client, login, monkeypatch):
    fake_model(
        monkeypatch,
        [
            model_response("general_chat"),
            model_response("get_assistant_info"),
            model_response(answer="这是工作台的智能助手。"),
        ],
    )
    login()
    output = events(workflow, new_run(client, question="你好，你是谁？"))
    final = output[-1]["data"]
    assert final["status"] == "completed"
    assert [s["name"] for s in final["steps"]] == [
        "model",
        "general_chat",
        "model",
        "get_assistant_info",
        "model",
    ]
    assert (
        "".join(e["data"]["text"] for e in output if e["type"] == "answer_delta") == final["result"]["answer"]
    )


def test_empty_business_evidence_cannot_be_bypassed_by_general_mode(workflow, client, login, monkeypatch):
    fake_model(
        monkeypatch,
        [
            model_response("general_chat"),
            model_response("search_knowledge", {"query": "不存在的产品规则"}),
            model_response(answer="随意编造产品保修一百年"),
        ],
    )
    login()
    output = events(workflow, new_run(client))
    assert not any(e["type"] == "answer_delta" for e in output)
    assert "编造" not in output[-1]["data"]["result"]["answer"]


def test_stop_mid_stream_preserves_partial_text_and_cannot_complete(workflow, client, login, monkeypatch):
    fake_model(
        monkeypatch,
        [model_response("general_chat"), model_response(answer="这段回复还没有生成完成，请继续阅读。")],
    )
    login()
    run = new_run(client)
    iterator = workflow.agent.execute(workflow.users["alice"], run["id"])
    first = next(e for e in iterator if e["type"] == "answer_delta")
    cancelled = workflow.agent.cancel_run(workflow.users["alice"], run["id"])
    assert cancelled["status"] == "cancelled" and cancelled["result"]["answer"] == first["data"]["text"]
    rest = list(iterator)
    assert not any(e["type"] == "answer_delta" for e in rest)
    assert rest[-1]["data"]["status"] == "cancelled"
    assert (
        client.get("/api/sessions/" + run["session"]).json()["messages"][-1]["content"]
        == first["data"]["text"]
    )


def test_disconnect_saves_last_received_partial_text(workflow, client, login, monkeypatch):
    fake_model(monkeypatch, [model_response("general_chat"), model_response(answer="收到的文字会保留。")])
    login()
    run = new_run(client)
    iterator = workflow.agent.execute(workflow.users["alice"], run["id"])
    first = next(e for e in iterator if e["type"] == "answer_delta")
    second = next(e for e in iterator if e["type"] == "answer_delta")
    iterator.close()
    final = workflow.agent.get_run(workflow.users["alice"], run["id"])
    assert final["status"] == "cancelled"
    assert final["result"]["answer"] == first["data"]["text"] + second["data"]["text"]


@pytest.mark.parametrize("finish", [None, "length"])
def test_truncated_stream_fails_without_claiming_complete(workflow, client, login, monkeypatch, finish):
    partial = model_response(answer="保留部分")
    partial.choices[0].finish_reason = finish
    fake_model(monkeypatch, [model_response("general_chat"), partial])
    login()
    final = execute(client, new_run(client))
    assert final["status"] == "failed" and final["error_code"] == "incomplete_response"
    assert final["result"]["answer"] == "保留部分"


def test_reasoning_fields_never_become_answer_events(workflow, client, login, monkeypatch):
    partial = model_response()
    partial.chunks = [
        SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    delta=SimpleNamespace(
                        content="只展示回答", tool_calls=None, reasoning_content="隐藏推理不应显示"
                    ),
                )
            ],
        )
    ]
    fake_model(monkeypatch, [model_response("general_chat"), partial])
    login()
    output = events(workflow, new_run(client))
    assert "隐藏推理" not in json.dumps(output, ensure_ascii=False)
    assert output[-1]["data"]["result"]["answer"] == "只展示回答"


def test_sse_endpoint_transports_incremental_answer_and_authoritative_final(
    workflow, client, login, monkeypatch
):
    fake_model(monkeypatch, [model_response("general_chat"), model_response(answer="你好，欢迎继续交流。")])
    login()
    run = new_run(client)
    response = client.post(f"/api/agent/runs/{run['id']}/stream")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.count("event: answer_delta") > 1
    assert response.text.index("event: answer_delta") < response.text.index("event: done")


def test_mixed_prose_and_tool_call_retracts_provisional_text(workflow, client, login, monkeypatch):
    mixed = model_response()
    mixed.chunks = [
        SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason=None, delta=SimpleNamespace(content="临时文字", tool_calls=None)
                )
            ],
        ),
        SimpleNamespace(
            usage=SimpleNamespace(total_tokens=20),
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="info-call",
                                function=SimpleNamespace(name="get_assistant_info", arguments="{}"),
                            )
                        ],
                    ),
                )
            ],
        ),
    ]
    fake_model(
        monkeypatch, [model_response("general_chat"), mixed, model_response(answer="重新依据公开信息回答。")]
    )
    login()
    output = events(workflow, new_run(client))
    visible = ""
    for event in output:
        if event["type"] == "answer_delta":
            assert event["data"]["offset"] == len(visible.encode("utf-16-le")) // 2
            visible += event["data"]["text"]
        elif event["type"] == "answer_reset":
            visible = ""
    assert any(e["type"] == "answer_reset" for e in output)
    assert visible == output[-1]["data"]["result"]["answer"] == "重新依据公开信息回答。"


def test_provider_exception_after_text_preserves_output_without_private_error(
    workflow, client, login, monkeypatch
):
    def broken_chunks():
        yield SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason=None, delta=SimpleNamespace(content="已经收到的文字", tool_calls=None)
                )
            ],
        )
        raise TimeoutError("private-provider-credential")

    partial = model_response()
    partial.chunks = broken_chunks()
    fake_model(monkeypatch, [model_response("general_chat"), partial])
    login()
    final = execute(client, new_run(client))
    assert final["status"] == "failed" and final["error_code"] == "provider_error"
    assert final["result"]["answer"] == "已经收到的文字"
    assert "private-provider-credential" not in json.dumps(final)
