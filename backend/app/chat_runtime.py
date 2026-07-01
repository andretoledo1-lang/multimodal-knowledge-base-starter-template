"""Chat provider runtime independent from KB storage."""
from __future__ import annotations

from dataclasses import dataclass

from .chat_models import (
    CHAT_MODEL_CLAUDE_OPUS,
    CHAT_MODEL_CLAUDE_SONNET,
    CHAT_MODEL_CODEX_OAUTH,
    CHAT_MODEL_DEEPSEEK,
    ChatModelId,
)
from .providers import ClaudeOAuthChatClient, CodexOAuthChatClient, DeepSeekChatClient, ProviderError


@dataclass(frozen=True)
class ChatRuntimeConfig:
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    codex_bin: str
    codex_oauth_model: str
    codex_oauth_reasoning_effort: str
    codex_oauth_timeout_s: float
    claude_bin: str
    claude_sonnet_model: str
    claude_opus_model: str
    claude_haiku_model: str
    claude_sonnet_effort: str
    claude_opus_effort: str
    claude_haiku_effort: str
    claude_judge_effort: str
    claude_oauth_timeout_s: float
    claude_oauth_premium_timeout_s: float
    claude_premium_repair_cap: int


class ChatRuntime:
    """Provider clients used by chat orchestration.

    This intentionally does not know about Chroma, Qdrant, package manifests, or
    retrieval backends. Retrieval is owned by `KbGateway`; model clients are
    owned here so KH-native mode can boot without constructing `KnowledgeBase`.
    """

    def __init__(self, config: ChatRuntimeConfig) -> None:
        self.chat_client = DeepSeekChatClient(
            api_key=config.deepseek_api_key,
            model=config.deepseek_model,
            base_url=config.deepseek_base_url,
        )
        self.codex_oauth_chat_client = CodexOAuthChatClient(
            codex_bin=config.codex_bin,
            model=config.codex_oauth_model,
            reasoning_effort=config.codex_oauth_reasoning_effort,
            timeout_s=config.codex_oauth_timeout_s,
        )
        self.claude_sonnet_chat_client = ClaudeOAuthChatClient(
            claude_bin=config.claude_bin,
            model=config.claude_sonnet_model,
            effort=config.claude_sonnet_effort,
            timeout_s=config.claude_oauth_timeout_s,
        )
        self.claude_opus_chat_client = ClaudeOAuthChatClient(
            claude_bin=config.claude_bin,
            model=config.claude_opus_model,
            effort=config.claude_opus_effort,
            timeout_s=config.claude_oauth_premium_timeout_s,
        )
        self.claude_haiku_worker_client = ClaudeOAuthChatClient(
            claude_bin=config.claude_bin,
            model=config.claude_haiku_model,
            effort=config.claude_haiku_effort,
            timeout_s=config.claude_oauth_timeout_s,
        )
        self.claude_sonnet_chief_client = ClaudeOAuthChatClient(
            claude_bin=config.claude_bin,
            model=config.claude_sonnet_model,
            effort=config.claude_sonnet_effort,
            timeout_s=config.claude_oauth_timeout_s,
        )
        self.claude_opus_judge_client = ClaudeOAuthChatClient(
            claude_bin=config.claude_bin,
            model=config.claude_opus_model,
            effort=config.claude_judge_effort,
            timeout_s=config.claude_oauth_timeout_s,
        )
        self.claude_premium_repair_cap = max(1, min(int(config.claude_premium_repair_cap), 2))

    def chat_client_for_model(self, chat_model: ChatModelId):
        if chat_model == CHAT_MODEL_DEEPSEEK:
            return self.chat_client
        if chat_model == CHAT_MODEL_CODEX_OAUTH:
            return self.codex_oauth_chat_client
        if chat_model == CHAT_MODEL_CLAUDE_SONNET:
            return self.claude_sonnet_chat_client
        if chat_model == CHAT_MODEL_CLAUDE_OPUS:
            return self.claude_opus_chat_client
        raise ProviderError(f"Unsupported chat model: {chat_model}")
