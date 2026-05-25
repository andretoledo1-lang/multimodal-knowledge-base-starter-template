import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiErrorMessage, type IngestResponse } from "@/lib/api";

export function useIngest() {
  const qc = useQueryClient();
  return useMutation<
    IngestResponse,
    Error,
    { files: File[]; tags?: string; videoFrameIntervalS?: number }
  >({
    mutationFn: ({ files, tags, videoFrameIntervalS }) =>
      api.ingest({
        files,
        tags,
        video_frame_interval_s: videoFrameIntervalS,
      }),
    onSuccess: (data) => {
      toast.success(
        `Ingested ${data.total} file${data.total === 1 ? "" : "s"}`,
      );
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (err) => toast.error(`Ingest failed: ${apiErrorMessage(err)}`),
  });
}
