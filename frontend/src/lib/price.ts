import type { Product } from "./types";

/** Price in the user's currency when the server converted it, else the listing's own. */
export function cmp(p: Product): { value: number; currency: string | null } | null {
  const raw = p.price_converted ?? p.price;
  if (raw === null) return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  return { value, currency: p.price_converted ? p.converted_currency : p.currency };
}
