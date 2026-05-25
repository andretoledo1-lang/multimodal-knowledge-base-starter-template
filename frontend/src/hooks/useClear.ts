import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";

export function useClear() {
  const qc = useQueryClient();
  return useMutation<{ cleared: boolean }, Error, void>({
    mutationFn: () => api.clear(),
    onSuccess: () => {
      toast.success("Knowledge base cleared");
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (err) => toast.error(`Clear failed: ${apiErrorMessage(err)}`),
  });
}
