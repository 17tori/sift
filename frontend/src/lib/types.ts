export type Mode = "exact" | "similar" | "cheaper" | "discover";

export interface Plan {
  code: string;
  title: string;
  description: string;
  price_stars: number;
  period_days: number;
  search_limit: number;
  limit_window: "day" | "month";
  priority: number;
  sort_order: number;
  is_active: boolean;
  features: {
    history_days?: number;
    favorites_limit?: number;
    advanced_filters?: boolean;
    modes?: Mode[];
    marketplaces?: "basic" | "all";
    max_candidates?: number;
    price_alerts?: boolean;
    deep_analysis?: boolean;
    early_access?: boolean;
    watch_limit?: number;
  };
}

export interface Subscription {
  id: number;
  plan_code: string;
  status: string;
  source: string;
  started_at: string;
  expires_at: string;
  is_recurring: boolean;
  auto_renew: boolean;
  canceled_at: string | null;
}

export interface Me {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string;
  photo_url: string | null;
  language_code: string | null;
  created_at: string;
  is_admin: boolean;
  plan: Plan;
  subscription: Subscription | null;
  quota: { used: number; limit: number; window: string; resets_at: string; bonus: number; remaining: number };
  trial: { available: boolean; active: boolean; used: boolean; ends_at: string | null; days: number };
  preferences: Preferences;
  total_searches: number;
  favorites_count: number;
}

export interface Preferences {
  theme?: "system" | "light" | "dark";
  currency?: string;
  country?: string;
  default_mode?: Mode;
  language?: "ru" | "en";
  view?: "grid" | "list";
}

export interface Marketplace {
  code: string;
  name: string;
  url: string;
  kind: string;
  state: "active" | "not_configured" | "no_legal_api" | "disabled" | "down";
  note: string;
  supports_image_search: boolean;
  regions: string[];
}

export interface AppConfig {
  brand: { name: string; tagline: string; tagline_ru: string; accent: string; support_username: string; support_email: string };
  bot_username: string;
  marketplaces: Marketplace[];
  upload: { max_bytes: number; formats: string[] };
  modes: Mode[];
  categories: string[];
}

export interface ProviderStatus {
  state: "searching" | "done" | "error" | "timeout" | "unavailable" | "skipped";
  count?: number;
  ms?: number;
  reason?: string;
}

export interface Analysis {
  is_product?: boolean;
  category?: string;
  subcategory?: string;
  title_en?: string;
  title_ru?: string;
  gender?: string;
  colors?: { name: string; hex: string }[];
  material?: string | null;
  pattern?: string | null;
  silhouette?: string | null;
  style?: string[];
  features?: string[];
  brand?: { name: string | null; confidence: string; evidence: string | null };
  palette?: { hex: string; share: number }[];
  vision_error?: string;
}

export interface Search {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: "uploaded" | "analyzing" | "embedding" | "searching" | "ranking" | "done";
  mode: Mode;
  created_at: string;
  finished_at: string | null;
  image_url: string | null;
  analysis: Analysis | null;
  providers: Record<string, ProviderStatus>;
  results_count: number;
  error: string | null;
  reference_price: string | null;
  reference_currency: string | null;
  has_similarity: boolean;
}

export interface Product {
  product_id: number;
  marketplace: string;
  marketplace_name: string;
  title: string;
  url: string;
  image_url: string | null;
  image_fallback_url: string | null;
  price: string | null;
  currency: string | null;
  price_converted: string | null;
  converted_currency: string | null;
  similarity: number | null;
  available: boolean | null;
  condition: string | null;
  brand: string | null;
  category: string | null;
  size: string | null;
  color: string | null;
  country: string | null;
  seller: string | null;
  is_favorite: boolean;
  via: "google_lens" | "web_search" | null;
}

export interface Results {
  items: Product[];
  total: number;
  next_offset: number | null;
  facets: Record<string, { value: string; count: number }[]>;
  filters_locked: boolean;
  price_range: PriceRange | null;
}

/** The same item (visually verified) on several marketplaces. */
export interface PriceRange {
  count: number;
  marketplaces: number;
  currency: string | null;
  min: Product;
  max: Product;
}

export interface Favorite {
  id: number;
  created_at: string;
  price_alert: boolean;
  saved_price: string | null;
  saved_currency: string | null;
  product: Product;
  collection_id: number | null;
  search_id: string | null;
}

export interface HistoryItem {
  id: string;
  status: Search["status"];
  mode: Mode;
  created_at: string;
  image_url: string | null;
  title: string | null;
  results_count: number;
}

export interface Payment {
  id: number;
  plan_code: string;
  amount_stars: number;
  currency: string;
  status: string;
  is_recurring: boolean;
  created_at: string;
  refunded_at: string | null;
}

export interface Referral {
  code: string;
  link: string;
  invited: number;
  purchased: number;
  earned_searches: number;
  reward_registration: number;
  reward_first_purchase: number;
  invitee_bonus: number;
}

export interface PricePoint {
  price: string;
  currency: string;
  at: string;
}

export interface Item {
  search_id: string;
  product: Product;
  offers: Product[];
  similar: Product[];
  price_history: PricePoint[];
  favorite_id: number | null;
  collection_id: number | null;
  watching: boolean;
}

export interface Collection {
  id: number;
  title: string;
  count: number;
  cover_url: string | null;
}

export interface Watch {
  id: number;
  search_id: string;
  title: string | null;
  image_url: string | null;
  active: boolean;
  best_price: string | null;
  best_currency: string | null;
  runs: number;
  last_run_at: string | null;
  last_found_at: string | null;
  last_search_id: string | null;
}

export interface Watches {
  items: Watch[];
  limit: number;
}

export interface Share {
  token: string;
  link: string;
  image_url: string;
  text: string;
  prepared_message_id: string | null;
}

export interface SharedFind {
  token: string;
  sharer_name: string;
  product: Product;
  search_id: string | null;
}

export interface GiftPack {
  code: string;
  searches: number;
  stars: number;
}

export interface Gift {
  code: string;
  pack: string;
  searches: number;
  status: "active" | "redeemed" | "refunded" | string;
  link: string;
  created_at: string;
  redeemed_at: string | null;
}

export interface Invoice {
  intent_id: string;
  invoice_link: string;
  amount_stars: number;
  recurring: boolean;
}

export interface GiftRedeemOut {
  searches: number;
  from_name: string;
}
