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
}

export interface Stats {
  total: number;
  by_modality: Record<string, number>;
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
  async stats(): Promise<Stats> {
    return jsonOrThrow(await fetch("/api/stats"));
  },

  async items(): Promise<ItemsResponse> {
    return jsonOrThrow(await fetch("/api/items"));
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
