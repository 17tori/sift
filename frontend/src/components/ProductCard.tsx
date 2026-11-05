import { motion } from "motion/react";
import { useState } from "react";
import { CONDITION_LABEL, money } from "../lib/format";
import { openExternal } from "../lib/telegram";
import type { Product } from "../lib/types";
import { IconHeart, IconImage } from "./icons";
import { cx } from "./ui";

function Similarity({ value }: { value: number }) {
  return (
    <span className="inline-flex h-6 items-center gap-1 rounded-full bg-black/55 px-2 font-mono text-[11px] font-medium text-white backdrop-blur"
      title="Визуальное сходство, рассчитанное моделью">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: value >= 75 ? "#7CE3A6" : value >= 45 ? "#F5F3EE" : "#A6A6A6" }} />
      {value}%
    </span>
  );
}

// Our stored copy of the photo the search found first, then the marketplace's own URL.
function Thumb({ srcs, alt }: { srcs: (string | null)[]; alt: string }) {
  const list = srcs.filter((u): u is string => !!u);
  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const src = list[idx];
  const ok = idx < list.length;
  return (
    <div className="relative h-full w-full overflow-hidden bg-surface-2">
      {ok && src ? (
        <img key={src} src={src} alt={alt} loading="lazy" decoding="async" referrerPolicy="no-referrer"
          onLoad={() => setLoaded(true)} onError={() => { setLoaded(false); setIdx((i) => i + 1); }}
          className={cx("h-full w-full object-cover transition-opacity duration-500", loaded ? "opacity-100" : "opacity-0")} />
      ) : (
        <div className="grid h-full w-full place-items-center text-ink-3"><IconImage size={28} /></div>
      )}
      {!loaded && ok && <div className="shimmer absolute inset-0" />}
    </div>
  );
}

export function ProductCard({ p, view, onFavorite }: { p: Product; view: "grid" | "list"; onFavorite: (on: boolean) => void }) {
  const fav = (
    <button aria-label={p.is_favorite ? "Убрать из избранного" : "В избранное"}
      onClick={(e) => { e.stopPropagation(); onFavorite(!p.is_favorite); }}
      className={cx("grid h-9 w-9 place-items-center rounded-full backdrop-blur transition-colors",
        p.is_favorite ? "bg-accent text-white" : "bg-black/45 text-white")}>
      <IconHeart size={17} filled={p.is_favorite} />
    </button>
  );
  const price = (
    <div className="flex items-baseline gap-1.5">
      {p.price === null && p.via
        ? <span className="text-[12px] font-medium text-ink-2">Цена на сайте</span>
        : <span className="font-mono text-[15px] font-semibold tracking-tight">{money(p.price, p.currency)}</span>}
      {p.price_converted && <span className="font-mono text-[11px] text-ink-3">≈ {money(p.price_converted, p.converted_currency)}</span>}
    </div>
  );
  const meta = (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3">
      <span className="font-semibold tracking-wide text-ink-2 uppercase">{p.marketplace_name}</span>
      {p.via && (
        <span title={p.via === "google_lens" ? "Найдено поиском Google по фото. Цена и наличие — на сайте площадки." : "Найдено веб-поиском. Цена — со страницы на момент индексации, проверьте на сайте."}>
          {p.via === "google_lens" ? "· по фото в Google" : "· веб-поиск"}
        </span>
      )}
      {p.condition && <span>{CONDITION_LABEL[p.condition] ?? p.condition}</span>}
      {p.available !== null && (
        <span className={cx("inline-flex items-center gap-1", p.available ? "text-good" : "text-bad")}>
          <span className="h-1.5 w-1.5 rounded-full bg-current" />{p.available ? "В наличии" : "Нет в наличии"}
        </span>
      )}
    </div>
  );

  if (view === "list") {
    return (
      <motion.article layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} onClick={() => openExternal(p.url)}
        className="flex cursor-pointer gap-3 rounded-[20px] bg-surface p-2.5 ring-1 ring-line active:scale-[0.99]">
        <div className="relative h-28 w-24 shrink-0 overflow-hidden rounded-2xl">
          <Thumb srcs={[p.image_url, p.image_fallback_url]} alt={p.title} />
          {p.similarity !== null && <div className="absolute bottom-1.5 left-1.5"><Similarity value={p.similarity} /></div>}
        </div>
        <div className="flex min-w-0 flex-1 flex-col py-1">
          {meta}
          <h3 className="mt-1 line-clamp-2 text-[14px] leading-snug">{p.title}</h3>
          <div className="mt-auto flex items-end justify-between">{price}{fav}</div>
        </div>
      </motion.article>
    );
  }
  return (
    <motion.article layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} onClick={() => openExternal(p.url)}
      className="cursor-pointer overflow-hidden rounded-[20px] bg-surface ring-1 ring-line active:scale-[0.99]">
      <div className="relative aspect-[4/5]">
        <Thumb srcs={[p.image_url, p.image_fallback_url]} alt={p.title} />
        <div className="absolute top-2 right-2">{fav}</div>
        {p.similarity !== null && <div className="absolute bottom-2 left-2"><Similarity value={p.similarity} /></div>}
      </div>
      <div className="space-y-1.5 p-3">
        {meta}
        <h3 className="line-clamp-2 min-h-[2.5em] text-[13px] leading-snug">{p.title}</h3>
        {price}
      </div>
    </motion.article>
  );
}

export function ProductSkeleton({ view }: { view: "grid" | "list" }) {
  if (view === "list") return <div className="flex gap-3 rounded-[20px] bg-surface p-2.5 ring-1 ring-line"><div className="shimmer h-28 w-24 rounded-2xl" /><div className="flex-1 space-y-2 py-2"><div className="shimmer h-3 w-1/3 rounded" /><div className="shimmer h-4 w-5/6 rounded" /><div className="shimmer h-4 w-1/2 rounded" /></div></div>;
  return <div className="overflow-hidden rounded-[20px] bg-surface ring-1 ring-line"><div className="shimmer aspect-[4/5]" /><div className="space-y-2 p-3"><div className="shimmer h-3 w-1/3 rounded" /><div className="shimmer h-4 w-full rounded" /><div className="shimmer h-4 w-1/2 rounded" /></div></div>;
}
