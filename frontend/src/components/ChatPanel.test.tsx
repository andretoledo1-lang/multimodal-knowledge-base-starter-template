import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/ChatPanel";
import type { ChatWorkspace } from "@/hooks/useChatWorkspace";
import { api, type ProviderStatusResponse } from "@/lib/api";

function providerPayload(
  claudeAvailable: boolean,
): ProviderStatusResponse {
  const checkedAt = "2026-08-13T00:00:00+00:00";
  const check = (state: string) => ({ state, checked_at: checkedAt });
  return {
    status: "verified",
    checked_at: checkedAt,
    providers: [
      {
        model_id: "deepseek-v4-pro",
        label: "deepseek - deepseek-v4-pro",
        provider_family: "deepseek",
        state: "ready",
        available: true,
        cause: "ready",
        retryable: false,
        recovery_hint: "Provider is ready.",
        auth: check("authenticated"),
        capacity: check("available"),
        last_smoke: { state: "not_run", checked_at: null },
      },
      {
        model_id: "codex-gpt-5.5-oauth",
        label: "openai/codex - gpt-5.5 OAuth",
        provider_family: "openai_codex",
        state: "authenticated_unverified",
        available: true,
        cause: "capacity_unverified",
        retryable: false,
        recovery_hint: "Authentication is valid, but execution capacity has not been smoke-tested.",
        auth: check("authenticated"),
        capacity: check("unknown"),
        last_smoke: { state: "not_run", checked_at: null },
      },
      ...["claude-sonnet-4-6-oauth", "claude-opus-4-8-oauth"].map(
        (modelId) => ({
          model_id: modelId,
          label:
            modelId === "claude-sonnet-4-6-oauth"
              ? "claude - sonnet-4.6 OAuth"
              : "claude - opus-4.8 OAuth Premium",
          provider_family: "anthropic",
          state: claudeAvailable
            ? ("authenticated_unverified" as const)
            : ("unavailable" as const),
          available: claudeAvailable,
          cause: claudeAvailable ? "capacity_unverified" : "auth_required",
          retryable: !claudeAvailable,
          recovery_hint: claudeAvailable
            ? "Authentication is valid, but execution capacity has not been smoke-tested."
            : "Sign in to this provider, then refresh provider status.",
          auth: check(claudeAvailable ? "authenticated" : "unauthenticated"),
          capacity: check("unknown"),
          last_smoke: { state: "not_run", checked_at: null },
        }),
      ),
    ],
  };
}

function workspace(model = "claude-sonnet-4-6-oauth") {
  return {
    selectedProjectId: "project-1",
    selectedThreadId: "thread-1",
    selectedThread: {
      id: "thread-1",
      title: "Provider test",
      chat_model: model,
      top_k: 5,
    },
    threadDetail: null,
    isCreatingThread: false,
    refreshThread: vi.fn(),
    createThread: vi.fn(),
  } as unknown as ChatWorkspace;
}

describe("ChatPanel provider readiness", () => {
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps an unavailable stored selection visible and blocks send until explicit choice", async () => {
    vi.spyOn(api, "chatProviders").mockResolvedValue(providerPayload(false));
    const user = userEvent.setup();
    render(<ChatPanel workspace={workspace()} />);

    const modelSelect = await screen.findByRole("combobox", { name: /model/i });
    await waitFor(() =>
      expect(modelSelect).toHaveValue("claude-sonnet-4-6-oauth"),
    );
    const providerRegion = screen.getByRole("region", {
      name: /Provider availability/i,
    });
    expect(
      within(providerRegion).getByText(
        /claude - sonnet-4.6 OAuth: auth required.*Sign in/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(providerRegion).getByText(
        /claude - opus-4.8 OAuth Premium: auth required.*Sign in/i,
      ),
    ).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Ask a question..."), "Hello");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await user.selectOptions(modelSelect, "deepseek-v4-pro");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("shows verification errors and offers an explicit refresh", async () => {
    vi.spyOn(api, "chatProviders")
      .mockRejectedValueOnce(new Error("network unavailable"))
      .mockResolvedValueOnce(providerPayload(true));
    const user = userEvent.setup();
    render(<ChatPanel workspace={workspace()} />);

    expect(
      await screen.findByText(/Provider verification failed/i),
    ).toBeInTheDocument();
    const refresh = screen.getByRole("button", {
      name: /Refresh provider status/i,
    });
    await user.click(refresh);

    expect(
      await screen.findByText(/authenticated; execution capacity is not smoke-tested/i),
    ).toBeInTheDocument();
  });

  it("bounds provider verification requests", async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => providerPayload(true),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.chatProviders();

    expect(timeoutSpy).toHaveBeenCalledWith(10_000);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat/providers",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("does not offer retry when every unavailable cause is nonretryable", async () => {
    const payload = providerPayload(true);
    payload.providers[0] = {
      ...payload.providers[0],
      state: "unavailable",
      available: false,
      cause: "billing_required",
      retryable: false,
      recovery_hint: "Review provider billing, then refresh provider status.",
      capacity: {
        state: "unavailable",
        checked_at: payload.checked_at,
      },
    };
    vi.spyOn(api, "chatProviders").mockResolvedValue(payload);
    render(<ChatPanel workspace={workspace("deepseek-v4-pro")} />);

    expect(
      await screen.findByText(/deepseek - deepseek-v4-pro: billing required/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Refresh provider status/i }),
    ).not.toBeInTheDocument();
  });

  it("sends the exact explicitly selected model without fallback", async () => {
    vi.spyOn(api, "chatProviders").mockResolvedValue(providerPayload(true));
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode("event: done\ndata: {}\n\n"),
          );
          controller.close();
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatPanel workspace={workspace("deepseek-v4-pro")} />);

    const modelSelect = await screen.findByRole("combobox", { name: /model/i });
    await user.selectOptions(modelSelect, "codex-gpt-5.5-oauth");
    await user.type(screen.getByPlaceholderText("Ask a question..."), "Use Codex");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      question: "Use Codex",
      chat_model: "codex-gpt-5.5-oauth",
      project_id: "project-1",
      thread_id: "thread-1",
    });
  });
});
