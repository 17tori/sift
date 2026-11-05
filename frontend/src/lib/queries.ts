import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { AppConfig, Favorite, Me, Plan, Preferences } from "./types";

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: () => api.get<AppConfig>("/api/v1/config"), staleTime: 300_000 });
export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/api/v1/me"), staleTime: 15_000 });
export const usePlans = () => useQuery({ queryKey: ["plans"], queryFn: () => api.get<Plan[]>("/api/v1/plans"), staleTime: 60_000 });
export const useFavorites = () => useQuery({ queryKey: ["favorites"], queryFn: () => api.get<Favorite[]>("/api/v1/favorites") });

export function usePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: Preferences) => api.patch<Me>("/api/v1/me/preferences", p as Record<string, unknown>),
    onSuccess: (me) => qc.setQueryData(["me"], me),
  });
}

export function useToggleFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ productId, searchId, on }: { productId: number; searchId?: string; on: boolean }) => {
      if (on) await api.post("/api/v1/favorites", { product_id: productId, search_id: searchId ?? null });
      else await api.del(`/api/v1/favorites/by-product/${productId}`);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["favorites"] });
      qc.invalidateQueries({ queryKey: ["results"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
