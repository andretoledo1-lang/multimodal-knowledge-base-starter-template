import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import type { SearchResult } from "@/lib/api";
import { parseSSE } from "@/lib/sse";

export interface ChatUserMessage {
  role: "user";
  content: string;
}

export interface ChatAssistantMessage {
  role: "assistant";
  content: string;
  sources?: SearchResult[];
  visualAttachments?: number;
  streaming?: boolean;
  error?: string;
}

export type ChatMessage = ChatUserMessage | ChatAssistantMessage;

interface ChatOptions {
  topK?: number;
  modalityFilter?: string[] | null;
  maxImages?: number;
}

interface SourcesPayload {
  sources: SearchResult[];
  visual_attachments: number;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setIsStreaming(false);
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "assistant" && last.streaming) {
        const next = prev.slice(0, -1);
        next.push({ ...last, streaming: false });
        return next;
      }
      return prev;
    });
  }, []);

  const send = useCallback(async (question: string, opts: ChatOptions = {}) => {
    const q = question.trim();
    // Use the live AbortController ref — not the closed-over `isStreaming`
    // state — so a rapid double-call within one render can't slip past.
    if (!q || abortRef.current) return;

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: q },
      { role: "assistant", content: "", streaming: true },
    ]);
    setIsStreaming(true);

    const updateAssistant = (
      patch: (m: ChatAssistantMessage) => ChatAssistantMessage,
    ) => {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== "assistant") return prev;
        const next = prev.slice(0, -1);
        next.push(patch(last));
        return next;
      });
    };

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          top_k: opts.topK ?? 5,
          modality_filter: opts.modalityFilter ?? null,
          max_images: opts.maxImages ?? 6,
        }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        const detail = await res.text().catch(() => res.statusText);
        throw new Error(detail || `HTTP ${res.status}`);
      }

      for await (const frame of parseSSE(res.body, ctrl.signal)) {
        if (frame.event === "message") {
          const token = safeJsonParse<string>(frame.data, "");
          if (token)
            updateAssistant((m) => ({ ...m, content: m.content + token }));
        } else if (frame.event === "sources") {
          const payload = safeJsonParse<SourcesPayload>(frame.data, {
            sources: [],
            visual_attachments: 0,
          });
          updateAssistant((m) => ({
            ...m,
            sources: payload.sources,
            visualAttachments: payload.visual_attachments,
          }));
        } else if (frame.event === "done") {
          updateAssistant((m) => ({ ...m, streaming: false }));
        } else if (frame.event === "error") {
          const payload = safeJsonParse<{ message?: string }>(frame.data, {});
          const msg = payload.message ?? "Stream error";
          updateAssistant((m) => ({
            ...m,
            streaming: false,
            error: msg,
          }));
          toast.error(`Chat error: ${msg}`);
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        updateAssistant((m) => ({ ...m, streaming: false }));
      } else {
        const msg = (err as Error).message;
        updateAssistant((m) => ({
          ...m,
          streaming: false,
          error: msg,
        }));
        toast.error(`Chat failed: ${msg}`);
      }
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  return { messages, isStreaming, send, reset, stop };
}

function safeJsonParse<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}
