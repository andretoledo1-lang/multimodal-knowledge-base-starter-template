import { useQuery } from "@tanstack/react-query";
import { api, type SearchResponse } from "@/lib/api";

export function useSearch(args: {
  query: string;
  topK: number;
  modalityFilter: string[] | null;
}) {
  const { query, topK, modalityFilter } = args;
  const enabled = query.trim().length > 0;
  return useQuery<SearchResponse>({
    queryKey: ["search", query, topK, modalityFilter],
    queryFn: () =>
      api.search({
        query,
        top_k: topK,
        modality_filter: modalityFilter,
      }),
    enabled,
    staleTime: 60_000,
  });
}
