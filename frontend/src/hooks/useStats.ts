import { useQuery } from "@tanstack/react-query";
import { api, type Stats } from "@/lib/api";

export function useStats() {
  return useQuery<Stats>({
    queryKey: ["stats"],
    queryFn: api.stats,
  });
}
