import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  MessageSquare,
  RotateCcw,
  Send,
  Square,
  User,
  Bot,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/EmptyState";
import { ModalityBadge } from "@/components/ModalityBadge";
import { PreviewThumb } from "@/components/PreviewThumb";
import {
  PreviewDialog,
  type PreviewDialogItem,
} from "@/components/PreviewDialog";
import { useChat, type ChatMessage } from "@/hooks/useChat";
import type { SearchResult } from "@/lib/api";

function Bubble({
  message,
  onSourceClick,
}: {
  message: ChatMessage;
  onSourceClick: (r: SearchResult) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={`max-w-[78%] rounded-lg border px-3.5 py-2.5 text-sm ${
          isUser ? "border-primary/30 bg-primary/10" : "bg-card"
        }`}
      >
        {message.content ? (
          <p className="whitespace-pre-wrap leading-relaxed">
            {message.content}
            {message.role === "assistant" && message.streaming && (
              <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-foreground/50 align-middle" />
            )}
          </p>
        ) : message.role === "assistant" && message.streaming ? (
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
          </span>
        ) : null}

        {message.role === "assistant" && message.error && (
          <p className="mt-2 text-xs text-destructive">{message.error}</p>
        )}

        {message.role === "assistant" &&
          message.sources &&
          message.sources.length > 0 && (
            <div className="mt-3 border-t pt-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Sources ({message.sources.length}
                {message.visualAttachments
                  ? ` · ${message.visualAttachments} visual`
                  : ""}
                )
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {message.sources.map((src) => (
                  <button
                    key={src.node_id}
                    type="button"
                    onClick={() => onSourceClick(src)}
                    className="flex items-center gap-2 rounded-md border bg-background p-2 text-left transition-colors hover:bg-accent"
                  >
                    <div className="h-10 w-10 shrink-0 overflow-hidden rounded bg-muted">
                      <PreviewThumb
                        url={src.preview_url}
                        modality={src.modality}
                        alt={src.display_name}
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium">
                        {src.display_name}
                      </div>
                      <div className="mt-0.5 flex items-center gap-1.5">
                        <ModalityBadge
                          modality={src.modality}
                          showLabel={false}
                        />
                        <span className="text-[10px] tabular-nums text-muted-foreground">
                          {(src.score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
      </div>
    </div>
  );
}

export function ChatPanel() {
  const { messages, isStreaming, send, reset, stop } = useChat();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const [previewItem, setPreviewItem] = useState<PreviewDialogItem | null>(
    null,
  );

  useEffect(() => {
    // Smooth scrolling per token queues dozens of animations and feels janky.
    // Snap-scroll while streaming, animate only when the stream settles.
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: isStreaming ? "auto" : "smooth",
    });
  }, [messages, isStreaming]);

  const submit = () => {
    const q = draft.trim();
    if (!q || isStreaming) return;
    setDraft("");
    void send(q);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <section className="flex h-full flex-col gap-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Chat</h2>
          <p className="text-sm text-muted-foreground">
            Grounded answers with cited sources from your knowledge base.
          </p>
        </div>
        {messages.length > 0 && (
          <Button variant="ghost" size="sm" onClick={reset}>
            <RotateCcw className="h-4 w-4" />
            New chat
          </Button>
        )}
      </header>

      <Card className="flex flex-1 flex-col overflow-hidden">
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-4"
          role="log"
          aria-live="polite"
        >
          {messages.length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title="Ask anything about your knowledge base"
              description="The assistant retrieves relevant items, looks at the visuals when helpful, and cites its sources."
              className="border-0 bg-transparent py-8"
            />
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((m, i) => (
                <Bubble
                  key={i}
                  message={m}
                  onSourceClick={(src) =>
                    setPreviewItem({
                      display_name: src.display_name,
                      modality: src.modality,
                      preview_url: src.preview_url,
                      snippet: src.snippet,
                      score: src.score,
                      metadata: src.metadata,
                    })
                  }
                />
              ))}
            </div>
          )}
        </div>

        <div className="border-t bg-card p-3">
          <div className="flex items-end gap-2">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask a question…  (Enter to send, Shift+Enter for newline)"
              rows={1}
              className="max-h-40 min-h-9 resize-none py-2 leading-5 field-sizing-content"
            />
            {isStreaming ? (
              <Button onClick={stop} variant="outline" aria-label="Stop">
                <Square className="h-4 w-4" />
                Stop
              </Button>
            ) : (
              <Button
                onClick={submit}
                disabled={draft.trim().length === 0}
                aria-label="Send"
              >
                <Send className="h-4 w-4" />
                Send
              </Button>
            )}
          </div>
        </div>
      </Card>

      <PreviewDialog
        open={previewItem !== null}
        onOpenChange={(v) => !v && setPreviewItem(null)}
        item={previewItem}
      />
    </section>
  );
}
