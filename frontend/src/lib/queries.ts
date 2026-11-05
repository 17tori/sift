import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { AppConfig, Collection, Favorite, Me, Plan, Preferences, Watches } from "./types";

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: () => api.get<AppConfig>("/api/v1/config"), staleTime: 300_000 });
export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/api/v1/me"), staleTime: 15_000 });
export const usePlans = () => useQuery({ queryKey: ["plans"], queryFn: () => api.get<Plan[]>("/api/v1/plans"), staleTime: 60_000 });
export const useFavorites = () => useQuery({ queryKey: ["favorites"], queryFn: () => api.get<Favorite[]>("/api/v1/favorites") });
export const useCollections = () => useQuery({ queryKey: ["collections"], queryFn: () => api.get<Collection[]>("/api/v1/collections") });
export const useWatches = () => useQuery({ queryKey: ["watches"], queryFn: () => api.get<Watches>("/api/v1/watches"), staleTime: 30_000 });

/** Start or stop watching a search; 402/403 come back as ApiError for the caller to explain. */
export function useWatchToggle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ searchId, on }: { searchId: string; on: boolean }) => {
      if (on) await api.post("/api/v1/watches", { search_id: searchId });
      else await api.del(`/api/v1/watches/by-search/${searchId}`);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["watches"] });
      qc.invalidateQueries({ queryKey: ["item"] });
    },
  });
}

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
      qc.invalidateQueries({ queryKey: ["item"] });
      qc.invalidateQueries({ queryKey: ["collections"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
