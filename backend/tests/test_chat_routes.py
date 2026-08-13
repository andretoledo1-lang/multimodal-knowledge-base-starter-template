from __future__ import annotations

import json

from app.kb_backends import KbBackendUnavailable
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


def test_no_result_answer_is_emitted_before_sources_and_done(tmp_path) -> None:
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
