import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ResultFilters {
  marketplace: string[];
  price_min: string;
  price_max: string;
  condition: string;
  country: string;
  category: string;
  color: string;
  size: string;
  sort: "relevance" | "similarity" | "price_asc" | "price_desc";
}

export const EMPTY_FILTERS: ResultFilters = {
  marketplace: [], price_min: "", price_max: "", condition: "", country: "", category: "", color: "", size: "",
  sort: "relevance",
};

interface UiState {
  view: "grid" | "list";
  activeSearchId: string | null;
  filters: Record<string, ResultFilters>;
  setView(v: "grid" | "list"): void;
  setActiveSearch(id: string | null): void;
  setFilters(searchId: string, f: ResultFilters): void;
}

const safeStorage = {
  getItem: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  setItem: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  removeItem: (k: string) => { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      view: "grid",
      activeSearchId: null,
      filters: {},
      setView: (view) => set({ view }),
      setActiveSearch: (activeSearchId) => set({ activeSearchId }),
      setFilters: (id, f) => set((s) => ({ filters: { ...Object.fromEntries(Object.entries(s.filters).slice(-20)), [id]: f } })),
    }),
    { name: "sift-ui", storage: { getItem: (k) => { const v = safeStorage.getItem(k); return v ? JSON.parse(v) : null; },
      setItem: (k, v) => safeStorage.setItem(k, JSON.stringify(v)), removeItem: safeStorage.removeItem } },
  ),
);
