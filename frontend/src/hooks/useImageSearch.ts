import { useMutation } from "@tanstack/react-query";
import { api, type SearchResponse } from "@/lib/api";

export function useImageSearch() {
  return useMutation<
    SearchResponse,
    Error,
    { file: File; topK?: number; modalityFilter?: string[] | null }
  >({
    mutationFn: ({ file, topK, modalityFilter }) =>
      api.searchImage({
        file,
        top_k: topK,
        modality_filter: modalityFilter ?? undefined,
      }),
  });
}
