// Minimal SSE frame parser for fetch+ReadableStream.
// EventSource is GET-only; our /api/chat takes a JSON body, so we
// hand-parse SSE frames here.

export interface SseFrame {
  event: string;
  data: string;
}

export async function* parseSSE(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseFrame> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      if (signal?.aborted) {
        await reader.cancel();
        return;
      }
      const { value, done } = await reader.read();
      if (done) {
        if (buf.trim()) yield parseFrame(buf);
        return;
      }
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        if (frame.trim()) yield parseFrame(frame);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): SseFrame {
  let event = "message";
  const dataLines: string[] = [];
  for (const raw of frame.split("\n")) {
    if (raw.startsWith("event:")) {
      event = raw.slice(6).trim();
    } else if (raw.startsWith("data:")) {
      // SSE spec: strip exactly one leading space if present
      const v = raw.slice(5);
      dataLines.push(v.startsWith(" ") ? v.slice(1) : v);
    }
  }
  return { event, data: dataLines.join("\n") };
}
