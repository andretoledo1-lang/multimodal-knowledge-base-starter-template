// Typed API client mirroring backend/app/schemas.py.

export interface SearchResult {
  node_id: string;
  score: number;
  modality: string;
  display_name: string;
  file_id: string;
  metadata: Record<string, unknown>;
  snippet: string;
  preview_url: string | null;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface IngestItem {
  file_id: string;
  original_name: string;
  modality: string;
  node_ids: string[];
  total_pages?: number | null;
  duration_seconds?: number | null;
  preview_url?: string | null;
}

export interface IngestResponse {
  items: IngestItem[];
  total: number;
}

export interface Item {
  file_id: string;
  original_name: string;
  modality: string;
  upload_time: string;
  node_ids: string[];
  preview_url: string | null;
}

export interface ItemsResponse {
  items: Item[];
  total: number;
  returned: number;
  limit: number | null;
  offset: number;
}

export interface Stats {
  total: number;
  by_modality: Record<string, number>;
}

export interface Project {
  id: string;
  name: string;
  memory: string;
  instructions: string;
  created_at: string;
  updated_at: string;
  thread_count: number;
  latest_thread_at: string | null;
}

export interface ProjectsResponse {
  projects: Project[];
}

export interface ChatThread {
  id: string;
  project_id: string;
  title: string;
  summary: string;
  chat_model: string | null;
  top_k: number | null;
  archived: boolean;
  pinned: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ThreadsResponse {
  threads: ChatThread[];
}

export interface PersistedChatMessage {
  id: string;
  thread_id: string;
  role: "user" | "assistant";
  content: string;
  chat_model: string | null;
  top_k: number | null;
  status: string;
  visual_attachments: number;
  citation_validation?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  sources: SearchResult[];
}

export interface ThreadDetail extends ChatThread {
  project: Project;
  messages: PersistedChatMessage[];
}

export interface WorkspaceBootstrapResponse {
  project: Project;
  thread: ChatThread;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export function apiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return String(err);
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async bootstrapWorkspace(): Promise<WorkspaceBootstrapResponse> {
    return jsonOrThrow(
      await fetch("/api/workspace/bootstrap", { method: "POST" }),
    );
  },

  async projects(): Promise<ProjectsResponse> {
    return jsonOrThrow(await fetch("/api/projects"));
  },

  async createProject(args: { name: string }): Promise<Project> {
    return jsonOrThrow(
      await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args),
      }),
    );
  },

  async updateProject(
    projectId: string,
    args: { name?: string; memory?: string; instructions?: string },
  ): Promise<Project> {
    return jsonOrThrow(
      await fetch(`/api/projects/${encodeURIComponent(projectId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args),
      }),
    );
  },

  async threads(
    projectId: string,
    args?: { include_archived?: boolean },
  ): Promise<ThreadsResponse> {
    const params = new URLSearchParams();
    if (args?.include_archived) params.set("include_archived", "true");
    const query = params.toString();
    return jsonOrThrow(
      await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/threads${query ? `?${query}` : ""}`,
      ),
    );
  },

  async createThread(args: {
    project_id: string;
    title?: string;
    chat_model?: string | null;
    top_k?: number | null;
  }): Promise<ChatThread> {
    return jsonOrThrow(
      await fetch("/api/threads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args),
      }),
    );
  },

  async updateThread(
    threadId: string,
    args: {
      title?: string;
      summary?: string;
      chat_model?: string | null;
      top_k?: number | null;
      archived?: boolean;
      pinned?: boolean;
    },
  ): Promise<ChatThread> {
    return jsonOrThrow(
      await fetch(`/api/threads/${encodeURIComponent(threadId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args),
      }),
    );
  },

  async thread(threadId: string): Promise<ThreadDetail> {
    return jsonOrThrow(await fetch(`/api/threads/${encodeURIComponent(threadId)}`));
  },

  async stats(): Promise<Stats> {
    return jsonOrThrow(await fetch("/api/stats"));
  },

  async items(args?: {
    limit?: number | null;
    offset?: number;
  }): Promise<ItemsResponse> {
    const params = new URLSearchParams();
    if (args?.limit != null) params.set("limit", String(args.limit));
    if (args?.offset != null && args.offset > 0) {
      params.set("offset", String(args.offset));
    }
    const query = params.toString();
    return jsonOrThrow(await fetch(`/api/items${query ? `?${query}` : ""}`));
  },

  async search(args: {
    query: string;
    top_k?: number;
    modality_filter?: string[] | null;
  }): Promise<SearchResponse> {
    return jsonOrThrow(
      await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args),
      }),
    );
  },

  async searchImage(args: {
    file: File;
    top_k?: number;
    modality_filter?: string[];
  }): Promise<SearchResponse> {
    const form = new FormData();
    form.append("file", args.file);
    if (args.top_k != null) form.append("top_k", String(args.top_k));
    if (args.modality_filter?.length) {
      form.append("modality_filter", args.modality_filter.join(","));
    }
    return jsonOrThrow(
      await fetch("/api/search/image", { method: "POST", body: form }),
    );
  },

  async ingest(args: {
    files: File[];
    tags?: string;
    video_frame_interval_s?: number;
  }): Promise<IngestResponse> {
    const form = new FormData();
    for (const f of args.files) form.append("files", f);
    if (args.tags) form.append("tags", args.tags);
    if (args.video_frame_interval_s != null) {
      form.append(
        "video_frame_interval_s",
        String(args.video_frame_interval_s),
      );
    }
    return jsonOrThrow(
      await fetch("/api/ingest", { method: "POST", body: form }),
    );
  },

  async deleteItem(fileId: string): Promise<{ deleted: number }> {
    return jsonOrThrow(
      await fetch(`/api/items/${encodeURIComponent(fileId)}`, {
        method: "DELETE",
      }),
    );
  },

  async clear(): Promise<{ cleared: boolean }> {
    return jsonOrThrow(await fetch("/api/clear", { method: "POST" }));
  },
};
