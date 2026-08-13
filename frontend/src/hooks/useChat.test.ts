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
});
