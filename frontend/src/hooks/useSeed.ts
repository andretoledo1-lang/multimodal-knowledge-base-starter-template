import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiErrorMessage, type IngestResponse } from "@/lib/api";

export function useSeed() {
  const qc = useQueryClient();
  return useMutation<IngestResponse, Error, void>({
    mutationFn: () => api.seed(),
    onSuccess: (data) => {
      toast.success(
        `Seeded ${data.total} sample item${data.total === 1 ? "" : "s"}`,
      );
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (err) => toast.error(`Seed failed: ${apiErrorMessage(err)}`),
  });
}
