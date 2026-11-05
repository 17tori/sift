import { type InfiniteData, type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CollectionPicker } from "../components/CollectionPicker";
import { CountUp, Photo, SectionMark, Stamp } from "../components/archive";
import { IconExternal, IconHeart, IconHanger } from "../components/icons";
import { PriceAxis } from "../components/PriceRange";
import { ProductCard } from "../components/ProductCard";
import { ShareSheet } from "../components/ShareSheet";
import { Sparkline } from "../components/Sparkline";
import { WatchButton } from "../components/WatchButton";
import { Button, cx, ErrorView, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { CONDITION_LABEL, money } from "../lib/format";
import { ease, rowVariants, spring } from "../lib/motion";
import { cmp } from "../lib/price";
import { useCollections, useToggleFavorite } from "../lib/queries";
import { haptic, openExternal } from "../lib/telegram";
import type { Favorite, Item as ItemT, Product, Results } from "../lib/types";

/** The card the user tapped is already in the cache: the hero renders on the first frame so the photo can fly in. */
function cachedProduct(qc: QueryClient, sid: string, pid: number): Product | undefined {
  for (const [, data] of qc.getQueriesData<InfiniteData<Results>>({ queryKey: ["results", sid] })) {
    const hit = data?.pages.flatMap((p) => p.items).find((x) => x.product_id === pid);
    if (hit) return hit;
  }
  for (const [, data] of qc.getQueriesData<ItemT>({ queryKey: ["item"] })) {
    const hit = data && [data.product, ...data.offers, ...data.similar].find((x) => x.product_id === pid);
    if (hit) return hit;
  }
  return qc.getQueryData<Favorite[]>(["favorites"])?.find((f) => f.product.product_id === pid)?.product;
}

function ShareIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 4v11M7.5 8.5 12 4l4.5 4.5M5 13v5.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V13" />
    </svg>
  );
}

function Action({ label, onClick, active, children }: { label: string; onClick: () => void; active?: boolean; children: React.ReactNode }) {
  return (
    <motion.button type="button" whileTap={{ scale: 0.94 }} transition={spring.bouncy} onClick={onClick} aria-pressed={active}
      className="flex flex-col items-center gap-1.5 text-[11px] font-medium text-ink-2">
      <span className={cx("grid h-12 w-12 place-items-center rounded-full transition-colors",
        active ? "bg-accent text-white" : "text-ink shadow-[inset_0_0_0_1px_var(--line-strong)]")}>{children}</span>
      {label}
    </motion.button>
  );
}

function OfferRow({ p, i, lowest, current, onOpen }: { p: Product; i: number; lowest: number | null; current: boolean; onOpen: () => void }) {
  const c = cmp(p);
  const best = c !== null && lowest !== null && c.value === lowest;
  return (
    <motion.li custom={i} variants={rowVariants} initial="hidden" animate="show">
      <button onClick={onOpen} disabled={current}
        className="flex min-h-[64px] w-full items-center gap-3 border-b border-line py-2.5 text-left active:bg-surface-2 disabled:active:bg-transparent">
        <span className="relative h-[52px] w-[42px] shrink-0 overflow-hidden rounded-[8px] shadow-[inset_0_0_0_1px_var(--line)]">
          <Photo src={p.image_url} fallback={p.image_fallback_url} alt="" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <Stamp muted={!best}>{p.marketplace_name}</Stamp>
            {current && <span className="caption text-ink-3">эта</span>}
            {best && <span className="caption text-accent">дешевле всех</span>}
          </span>
          <span className="mt-1 block truncate text-[13px] text-ink-2">{p.title}</span>
        </span>
        <span className="text-right">
          <span className={cx("block font-mono text-[15px] font-semibold tnum", best && "text-accent")}>{c ? money(c.value, c.currency) : "—"}</span>
          {p.similarity !== null && <span className="font-mono text-[10px] text-ink-3">сходство {p.similarity}%</span>}
        </span>
      </button>
    </motion.li>
  );
}

export default function Item() {
  const { sid = "", pid = "0" } = useParams();
  const productId = Number(pid);
  const qc = useQueryClient();
  const nav = useNavigate();
  const reduce = useReducedMotion();
  const fav = useToggleFavorite();
  const cols = useCollections();
  const [share, setShare] = useState(false);
  const [pick, setPick] = useState(false);
  const q = useQuery({
    queryKey: ["item", sid, productId],
    queryFn: () => api.get<ItemT>(`/api/v1/searches/${sid}/items/${productId}`),
  });
  const placeholder = q.data?.product ?? cachedProduct(qc, sid, productId);
  const { scrollY } = useScroll();
  const photoY = useTransform(scrollY, [0, 400], [0, reduce ? 0 : 60]);
  const photoScale = useTransform(scrollY, [-120, 0], [reduce ? 1 : 1.08, 1]);

  if (q.isError && !placeholder) return <ErrorView error={q.error} retry={() => q.refetch()} />;
  const it = q.data;
  const p = placeholder;
  const open = (x: Product) => { haptic.tap(); nav(`/search/${sid}/item/${x.product_id}`); };
  const all = it ? [it.product, ...it.offers] : [];
  const priced = all.map(cmp).filter((c): c is NonNullable<typeof c> => !!c);
  const lowest = priced.length ? Math.min(...priced.map((c) => c.value)) : null;
  const sorted = [...all].sort((a, b) => (cmp(a)?.value ?? Infinity) - (cmp(b)?.value ?? Infinity));
  const price = p ? cmp(p) : null;
  const firstPrice = it?.price_history[0];
  const dropped = price && firstPrice && firstPrice.currency === (p?.currency ?? "") && Number(firstPrice.price) > Number(p?.price);
  const collection = it?.collection_id ? cols.data?.find((c) => c.id === it.collection_id) : undefined;
  const meta = p ? [p.brand, p.condition && (CONDITION_LABEL[p.condition] ?? p.condition), p.size, p.color, p.seller].filter(Boolean) as string[] : [];

  return (
    <div className="mx-auto max-w-xl" style={{ paddingBottom: "calc(96px + var(--tg-safe-bottom, 0px))" }}>
      <div className="px-5 pt-1">
        <motion.div layoutId={`thumb-${productId}`} transition={spring.soft}
          className="relative aspect-[4/5] overflow-hidden rounded-[22px] bg-surface-2 shadow-[inset_0_0_0_1px_var(--line)]">
          {p ? (
            <motion.div className="absolute inset-0" style={{ y: photoY, scale: photoScale }}>
              <Photo src={p.image_url} fallback={p.image_fallback_url} alt={p.title} grayscale={p.available === false} />
            </motion.div>
          ) : <Skeleton className="absolute inset-0" />}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/25 via-transparent via-30% to-transparent" />
          {p && <div className="absolute top-3.5 left-3.5"><Stamp onPhoto land className="bg-black/25 backdrop-blur-[6px]">{p.available === false ? "Снято" : p.marketplace_name}</Stamp></div>}
          {p?.similarity != null && (
            <motion.span initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
              title="Визуальное сходство, рассчитанное моделью"
              className="absolute bottom-3.5 left-3.5 inline-flex h-7 items-center gap-1.5 rounded-full bg-black/60 px-2.5 font-mono text-[12px] text-[#F5F3EE] backdrop-blur">
              сходство <CountUp value={p.similarity} suffix="%" delay={0.3} />
            </motion.span>
          )}
        </motion.div>

        {p && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.42, ease: ease.outExpo, delay: 0.12 }}>
            <p className="inv mt-4">№ {String(p.product_id % 10000).padStart(4, "0")} · {p.marketplace_name}{p.via === "google_lens" ? " · По фото в Google" : ""}</p>
            <h1 className="mt-2 font-serif text-[30px] leading-[33px] font-light tracking-[-0.01em]">{p.title}</h1>
            {meta.length > 0 && <p className="caption mt-2.5 text-ink-3">{meta.join(" · ")}</p>}
            <div className="mt-4 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              {price ? (
                <>
                  <span className="font-mono text-[30px] font-semibold tracking-[-0.02em] tnum">{money(price.value, price.currency)}</span>
                  {p.price_converted && p.converted_currency !== p.currency && <span className="font-mono text-[13px] text-ink-3">{money(p.price, p.currency)} на площадке</span>}
                  {dropped && <span className="font-mono text-[13px] text-good">было {money(firstPrice.price, firstPrice.currency)}</span>}
                </>
              ) : <span className="font-serif text-[22px] text-ink-2 italic">Цена на сайте</span>}
            </div>
          </motion.div>
        )}

        <motion.div className="mt-6 grid grid-cols-3 gap-2 border-y border-line py-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2, duration: 0.3 }}>
          <Action label={p?.is_favorite ? "Сохранено" : "Сохранить"} active={!!p?.is_favorite}
            onClick={() => p && fav.mutate({ productId, searchId: sid, on: !p.is_favorite })}>
            <IconHeart size={19} filled={!!p?.is_favorite} />
          </Action>
          <Action label={collection ? collection.title.slice(0, 14) : "В коллекцию"} active={!!collection} onClick={() => setPick(true)}>
            <IconHanger size={19} />
          </Action>
          <Action label="Открытка" onClick={() => setShare(true)}><ShareIcon size={19} /></Action>
        </motion.div>
        <div className="mt-4 flex justify-center"><WatchButton searchId={sid} watching={it?.watching} /></div>
      </div>

      {it && it.offers.length > 0 && (
        <section className="mt-8 px-5">
          <SectionMark numeral="I" label="Цены на площадках" right={<span className="caption text-ink-3">{all.length}</span>} />
          <p className="mt-2 text-[12px] leading-[17px] text-ink-2">Та же вещь, сверенная по фото. Сначала самые дешёвые.</p>
          <PriceAxis offers={sorted} current={productId} onPick={(x) => x.product_id !== productId && open(x)} />
          <ul className="mt-2 border-t border-line">
            {sorted.map((x, i) => <OfferRow key={x.product_id} p={x} i={i} lowest={lowest} current={x.product_id === productId} onOpen={() => open(x)} />)}
          </ul>
        </section>
      )}

      {it && it.price_history.length >= 2 && (
        <section className="mt-8 px-5">
          <SectionMark numeral={it.offers.length ? "II" : "I"} label="История цены" />
          <div className="mt-3"><Sparkline points={it.price_history} /></div>
        </section>
      )}

      {it && it.similar.length > 0 && (
        <section className="mt-8 px-5">
          <SectionMark numeral={["I", "II", "III"][(it.offers.length ? 1 : 0) + (it.price_history.length >= 2 ? 1 : 0)]} label="Похожие" />
          <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-6">
            {it.similar.map((x, i) => (
              <ProductCard key={x.product_id} p={x} view="grid" index={i} onOpen={() => open(x)}
                onFavorite={(on) => fav.mutate({ productId: x.product_id, searchId: sid, on })} />
            ))}
          </div>
        </section>
      )}

      {!it && q.isPending && <div className="mt-8 space-y-3 px-5"><Skeleton className="h-5 w-40" /><Skeleton className="h-16" /><Skeleton className="h-16" /></div>}

      {p && (
        <motion.div className="fixed inset-x-0 bottom-0 z-30 bg-gradient-to-t from-bg via-bg to-transparent px-5 pt-6"
          style={{ paddingBottom: "calc(14px + var(--tg-safe-bottom, 0px))" }}
          initial={{ y: 80 }} animate={{ y: 0 }} transition={{ ...spring.soft, delay: 0.25 }}>
          <div className="mx-auto max-w-xl">
            <Button className="w-full" onClick={() => openExternal(p.url)}>Открыть на {p.marketplace_name} <IconExternal size={17} /></Button>
          </div>
        </motion.div>
      )}

      <ShareSheet open={share} onClose={() => setShare(false)} productId={productId} searchId={sid} />
      <CollectionPicker open={pick} onClose={() => setPick(false)} favoriteId={it?.favorite_id ?? null} productId={productId}
        searchId={sid} current={it?.collection_id ?? null} />
    </div>
  );
}
