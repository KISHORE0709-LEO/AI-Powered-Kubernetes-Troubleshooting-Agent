import { useQuery } from "@tanstack/react-query";
import { getInvestigationHistory } from "@/services/history";

export function useInvestigationHistory(userId: string) {
  return useQuery({
    queryKey: ["investigation-history", userId],
    queryFn: getInvestigationHistory,
    staleTime: 30_000,
  });
}
