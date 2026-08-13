from __future__ import annotations

import json

from app.kb_backends import KbBackendUnavailable
from app.kb import SearchResult
from app.providers import ProviderError
from app.rag import GroundedAnswer
from app.routes import chat as chat_module
from app.routes.chat import _stream
from app.schemas import ChatRequest
from app.chat_store import ChatStore


class FailingKb:
    def search_text(self, *_args, **_kwargs):
        raise KbBackendUnavailable("/Users/vidigal/private/token")


class EmptyKb:
    def search_text(self, *_args, **_kwargs):
        return []

    def chat_client_for_model(self, *_args, **_kwargs):
        raise AssertionError("No-result chat must not call a provider")


def test_chat_stream_redacts_kb_backend_errors() -> None:
    frames = list(_stream(FailingKb(), ChatRequest(question="x"), store=object()))
    payload = "".join(frames)

    assert "Knowledge base backend unavailable." in payload
    assert "/Users/vidigal/private" not in payload
    assert "token" not in payload


def test_no_result_answer_is_emitted_before_sources_and_done(
    tmp_path, monkeypatch
) -> None:
    cleared: list[str] = []
    monkeypatch.setattr(chat_module, "clear_runtime_failure", cleared.append)
    frames = list(
        _stream(
            EmptyKb(),
            ChatRequest(question="missing"),
            store=ChatStore(tmp_path / "chat.sqlite"),
        )
    )

    assert frames[0].startswith("data: \"I couldn't find anything relevant")
    assert "event: sources" in frames[1]
    assert '"sources": []' in frames[1]
    assert frames[2] == "event: done\ndata: {}\n\n"
    assert cleared == []


def test_no_result_thread_persists_exact_emitted_answer(tmp_path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite")
    project = store.create_project(name="Dante")
    thread = store.create_thread(project_id=project["id"])
    frames = list(
        _stream(
            EmptyKb(),
            ChatRequest(question="missing", project_id=project["id"], thread_id=thread["id"]),
            store=store,
        )
    )

    emitted = json.loads(frames[0].split("data: ", 1)[1])
    detail = store.get_thread_detail(thread["id"])
    assert detail["messages"][-1]["content"] == emitted


def test_provider_error_records_overlay_and_grounded_success_clears_it(tmp_path, monkeypatch) -> None:
    recorded: list[tuple[str, str]] = []
    cleared: list[str] = []
    monkeypatch.setattr(chat_module, "record_runtime_failure", lambda model, cause: recorded.append((model, cause)))
    monkeypatch.setattr(chat_module, "clear_runtime_failure", cleared.append)

    def provider_failure(*_args, **_kwargs):
        raise ProviderError("private upstream detail", cause="rate_limited")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_module, "answer_with_vision", provider_failure)
    failure_frames = list(
        _stream(EmptyKb(), ChatRequest(question="fail"), ChatStore(tmp_path / "chat.sqlite"))
    )

    assert recorded == [("deepseek-v4-pro", "rate_limited")]
    assert "rate_limited" in "".join(failure_frames)
    assert cleared == []

    def grounded_success(*_args, **_kwargs):
        yield GroundedAnswer(
            answer="Grounded answer [1].",
            sources=[
                SearchResult(
                    node_id="node-a",
                    score=0.9,
                    modality="text",
                    metadata={"id": "source-a"},
                    snippet="source text",
                )
            ],
            visual_attachments=0,
        )

    monkeypatch.setattr(chat_module, "answer_with_vision", grounded_success)
    list(_stream(EmptyKb(), ChatRequest(question="ok"), ChatStore(tmp_path / "chat-ok.sqlite")))

    assert cleared == ["deepseek-v4-pro"]
