import { useRef } from "react";
import {
  Database,
  Trash2,
  Sparkles,
  Upload,
  Moon,
  Sun,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ModalityBadge } from "@/components/ModalityBadge";
import { useStats } from "@/hooks/useStats";
import { useSeed } from "@/hooks/useSeed";
import { useClear } from "@/hooks/useClear";
import { useIngest } from "@/hooks/useIngest";
import { useTheme } from "@/components/theme-provider";
import { type Modality } from "@/lib/utils";

const MODALITIES: Modality[] = ["image", "pdf", "video", "text"];

export function Sidebar() {
  const { data: stats, isLoading } = useStats();
  const seed = useSeed();
  const clear = useClear();
  const ingest = useIngest();
  const { resolved, toggle } = useTheme();
  const fileInput = useRef<HTMLInputElement>(null);

  const total = stats?.total ?? 0;

  const onPickFiles = () => fileInput.current?.click();
  const onFilesChosen = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    ingest.mutate({ files });
    e.target.value = "";
  };

  const onClear = () => {
    if (total === 0) return;
    if (
      window.confirm(
        `Permanently delete all ${total} items from the knowledge base?`,
      )
    ) {
      clear.mutate();
    }
  };

  return (
    <aside className="flex h-screen w-80 shrink-0 flex-col border-r bg-card">
      <div className="flex h-[60px] shrink-0 items-center gap-2.5 border-b px-5">
        <div className="rounded-md bg-primary/10 p-1.5 text-primary">
          <Database className="h-5 w-5" />
        </div>
        <div className="flex min-w-0 flex-col leading-tight">
          <span className="text-sm font-semibold">Multimodal KB</span>
          <span className="truncate text-[11px] text-muted-foreground">
            Cross-modal RAG over your data
          </span>
        </div>
      </div>

      <div className="px-5 py-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Knowledge base
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          {isLoading ? (
            <Skeleton className="h-7 w-12" />
          ) : (
            <span className="text-2xl font-semibold tabular-nums">{total}</span>
          )}
          <span className="text-sm text-muted-foreground">
            {total === 1 ? "item" : "items"}
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-1.5">
          {isLoading
            ? Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-6" />
              ))
            : MODALITIES.map((m) => {
                const count = stats?.by_modality?.[m] ?? 0;
                return (
                  <div
                    key={m}
                    className="flex items-center justify-between rounded-md border bg-background px-2 py-1"
                  >
                    <ModalityBadge modality={m} />
                    <span className="text-xs font-medium tabular-nums text-muted-foreground">
                      {count}
                    </span>
                  </div>
                );
              })}
        </div>
      </div>

      <Separator />

      <div className="flex flex-col gap-2 px-5 py-4">
        <Button
          onClick={onPickFiles}
          disabled={ingest.isPending}
          className="w-full justify-start"
        >
          {ingest.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          {ingest.isPending ? "Uploading…" : "Upload files"}
        </Button>
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          onChange={onFilesChosen}
          accept="image/*,.pdf,video/*,.txt,.md,.markdown,.json,.csv,.html,.htm"
        />

        <Button
          variant="outline"
          onClick={() => seed.mutate()}
          disabled={seed.isPending}
          className="w-full justify-start"
        >
          {seed.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          {seed.isPending ? "Loading…" : "Load demo data"}
        </Button>

        <Button
          variant="ghost"
          onClick={onClear}
          disabled={clear.isPending || total === 0}
          className="w-full justify-start text-destructive hover:bg-destructive/10 hover:text-destructive"
        >
          {clear.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
          Clear all
        </Button>
      </div>

      <div className="mt-auto border-t px-5 py-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Theme</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggle}
            aria-label="Toggle theme"
          >
            {resolved === "dark" ? (
              <>
                <Sun className="h-4 w-4" /> Light
              </>
            ) : (
              <>
                <Moon className="h-4 w-4" /> Dark
              </>
            )}
          </Button>
        </div>
      </div>
    </aside>
  );
}
