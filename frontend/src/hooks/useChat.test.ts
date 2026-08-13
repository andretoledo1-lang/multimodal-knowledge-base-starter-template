import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useChat } from "@/hooks/useChat";

describe("useChat SSE completion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("finalizes an empty assistant message when the stream ends without done", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, body }),
    );
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.send("Question");
    });

    const assistant = result.current.messages.at(-1);
    expect(assistant).toMatchObject({
      role: "assistant",
      content: "Chat ended without an answer. Please retry.",
      streaming: false,
      error: "The chat stream ended before completion.",
    });
    expect(result.current.isStreaming).toBe(false);
  });

  it("refreshes provider status only for classified provider errors", async () => {
    const onProviderFailure = vi.fn();
    const responseFor = (data: object) => ({
      ok: true,
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode(
              `event: error\ndata: ${JSON.stringify(data)}\n\nevent: done\ndata: {}\n\n`,
            ),
          );
          controller.close();
        },
      }),
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(responseFor({ message: "KB unavailable" }))
      .mockResolvedValueOnce(
        responseFor({ message: "Provider unavailable", cause: "auth_required" }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useChat({ onProviderFailure }));

    await act(async () => {
      await result.current.send("First");
    });
    expect(onProviderFailure).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.send("Second");
    });
    expect(onProviderFailure).toHaveBeenCalledTimes(1);
  });
});
