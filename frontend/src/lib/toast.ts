import { create } from "zustand";

export interface ToastItem {
  id: number;
  text: string;
  tone: "neutral" | "good" | "bad";
}

interface ToastState {
  items: ToastItem[];
  push(text: string, tone?: ToastItem["tone"]): void;
  drop(id: number): void;
}

let seq = 0;
export const useToast = create<ToastState>()((set) => ({
  items: [],
  push: (text, tone = "neutral") => {
    const id = ++seq;
    set((s) => ({ items: [...s.items.slice(-2), { id, text, tone }] }));
    window.setTimeout(() => set((s) => ({ items: s.items.filter((x) => x.id !== id) })), 2600);
  },
  drop: (id) => set((s) => ({ items: s.items.filter((x) => x.id !== id) })),
}));

export const toast = (text: string, tone?: ToastItem["tone"]) => useToast.getState().push(text, tone);
