import {
  useRef,
  useEffect,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  Archive,
  Folder,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Save,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ModalityBadge } from "@/components/ModalityBadge";
import { useStats } from "@/hooks/useStats";
import { useClear } from "@/hooks/useClear";
import { useIngest } from "@/hooks/useIngest";
import type { ChatWorkspace } from "@/hooks/useChatWorkspace";
import { type Modality } from "@/lib/utils";

const MODALITIES: Modality[] = ["image", "pdf", "video", "text"];

interface SidebarProps {
  width: number;
  onResizeStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
  workspace: ChatWorkspace;
}

export function Sidebar({ width, onResizeStart, workspace }: SidebarProps) {
  const { data: stats, isLoading } = useStats();
  const clear = useClear();
  const ingest = useIngest();
  const fileInput = useRef<HTMLInputElement>(null);
  const [memoryDraft, setMemoryDraft] = useState("");
  const [isAddingProject, setIsAddingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const sidebarStyle = {
    "--sidebar-width": `${width}px`,
  } as CSSProperties;

  const hasStats = stats != null;
  const total = stats?.total ?? 0;
  const canClear = hasStats && total > 0;

  const onPickFiles = () => fileInput.current?.click();
  useEffect(() => {
    setMemoryDraft(workspace.selectedProject?.memory ?? "");
  }, [workspace.selectedProject?.id, workspace.selectedProject?.memory]);

  const defaultProjectName = () => `Project ${workspace.projects.length + 1}`;

  const onCreateProject = () => {
    setNewProjectName(defaultProjectName());
    setIsAddingProject(true);
  };

  const onCancelProjectCreation = () => {
    if (workspace.isCreatingProject) return;
    setNewProjectName("");
    setIsAddingProject(false);
  };

  const onSubmitProjectCreation = () => {
    if (workspace.isCreatingProject) return;
    const name = newProjectName.trim() || defaultProjectName();
    workspace.createProject(name, {
      onSuccess: () => {
        setNewProjectName("");
        setIsAddingProject(false);
      },
    });
  };

  const onRenameProject = () => {
    const current = workspace.selectedProject?.name ?? "";
    const name = window.prompt("Project name", current)?.trim();
    if (name && name !== current) workspace.renameProject(name);
  };

  const onRenameThread = (threadId: string, currentTitle: string) => {
    const title = window.prompt("Thread title", currentTitle)?.trim();
    if (title && title !== currentTitle) workspace.renameThread(threadId, title);
  };

  const onFilesChosen = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    ingest.mutate({ files });
    e.target.value = "";
  };

  const onClear = () => {
    if (!canClear) return;
    if (
      window.confirm(
        `Permanently delete all ${total} items from the knowledge base?`,
      )
    ) {
      clear.mutate();
    }
  };

  return (
    <aside
      style={sidebarStyle}
      className="app-sidebar comfortable-scrollbar relative flex max-h-[44vh] w-full shrink-0 flex-col overflow-y-auto border-b bg-card md:h-screen md:max-h-none md:w-[var(--sidebar-width)] md:border-b-0 md:border-r"
    >
      <div className="app-sidebar-brand shrink-0 border-b border-border/60" />

      <div className="comfortable-scrollbar flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
        <section className="shrink-0">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Projects
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={onCreateProject}
              disabled={
                workspace.isLoading || workspace.isCreatingProject || isAddingProject
              }
              aria-label="New project"
            >
              {workspace.isCreatingProject ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
          {isAddingProject && (
            <div className="mb-2 flex items-center gap-1 rounded-md border border-primary/35 bg-background/60 p-1">
              <Input
                autoFocus
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    onSubmitProjectCreation();
                  }
                  if (event.key === "Escape") {
                    event.preventDefault();
                    onCancelProjectCreation();
                  }
                }}
                placeholder="Project name"
                className="h-7 min-w-0 flex-1 px-2 text-xs"
                aria-label="Project name"
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                onClick={onSubmitProjectCreation}
                disabled={workspace.isCreatingProject}
                aria-label="Create project"
              >
                {workspace.isCreatingProject ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                onClick={onCancelProjectCreation}
                disabled={workspace.isCreatingProject}
                aria-label="Cancel project creation"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
          <div className="flex max-h-28 flex-col gap-1 overflow-y-auto pr-1">
            {workspace.projects.length === 0 && workspace.isLoading ? (
              <>
                <Skeleton className="h-8" />
                <Skeleton className="h-8" />
              </>
            ) : (
              workspace.projects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => workspace.selectProject(project)}
                  className={`flex min-h-8 items-center gap-2 rounded-md border px-2 py-1.5 text-left text-sm transition-colors ${
                    workspace.selectedProjectId === project.id
                      ? "border-primary/45 bg-primary/15 text-foreground"
                      : "border-border/60 bg-background/45 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Folder className="h-3.5 w-3.5 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{project.name}</span>
                  <span className="shrink-0 text-[10px] tabular-nums">
                    {project.thread_count}
                  </span>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="shrink-0">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Threads
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => workspace.createThread()}
              disabled={!workspace.selectedProjectId || workspace.isCreatingThread}
              aria-label="New thread"
            >
              {workspace.isCreatingThread ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
          <div className="comfortable-scrollbar flex max-h-44 flex-col gap-1 overflow-y-auto pr-1 md:max-h-52">
            {workspace.threads.length === 0 && workspace.isLoading ? (
              <>
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </>
            ) : (
              workspace.threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`group flex min-h-10 items-center gap-1 rounded-md border px-2 py-1.5 transition-colors ${
                    workspace.selectedThreadId === thread.id
                      ? "border-primary/45 bg-primary/15"
                      : "border-border/60 bg-background/45"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => workspace.selectThread(thread)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate text-sm">
                      {thread.title}
                    </span>
                    {thread.message_count > 0 && (
                      <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
                        {thread.message_count}
                      </span>
                    )}
                  </button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={() => onRenameThread(thread.id, thread.title)}
                    aria-label="Rename thread"
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={() => workspace.archiveThread(thread.id)}
                    aria-label="Archive thread"
                  >
                    <Archive className="h-3 w-3" />
                  </Button>
                </div>
              ))
            )}
          </div>
        </section>

        {workspace.selectedProject && (
          <section className="shrink-0 rounded-md border bg-background/35 p-2">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-xs font-semibold">
                  {workspace.selectedProject.name}
                </div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Project memory
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={onRenameProject}
                  aria-label="Rename project"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() =>
                    workspace.updateProjectMemory(
                      memoryDraft,
                      workspace.selectedProject?.instructions,
                    )
                  }
                  disabled={workspace.isUpdatingProject}
                  aria-label="Save project memory"
                >
                  {workspace.isUpdatingProject ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
            </div>
            <Textarea
              value={memoryDraft}
              onChange={(event) => setMemoryDraft(event.target.value)}
              placeholder="Key decisions, preferences, constraints..."
              rows={3}
              className="min-h-20 resize-none text-xs"
            />
          </section>
        )}
      </div>

      <Separator />

      <div className="px-5 py-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Knowledge base
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          {isLoading || !hasStats ? (
            <Skeleton className="h-7 w-12" />
          ) : (
            <span className="text-2xl font-semibold tabular-nums">{total}</span>
          )}
          <span className="text-sm text-muted-foreground">
            {total === 1 ? "item" : "items"}
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-1.5">
          {isLoading || !hasStats
            ? Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-6" />
              ))
            : MODALITIES.map((m) => {
                const count = stats?.by_modality?.[m] ?? 0;
                return (
                  <div
                    key={m}
                    className="surface-card flex items-center justify-between rounded-md border bg-background/60 px-2 py-1"
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
          variant="ghost"
          onClick={onClear}
          disabled={clear.isPending || !canClear}
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

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize navigation sidebar"
        className="app-resize-handle app-resize-handle-left hidden md:block"
        onPointerDown={onResizeStart}
      />
    </aside>
  );
}
