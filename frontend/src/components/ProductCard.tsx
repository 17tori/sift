import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { CONDITION_LABEL, money } from "../lib/format";
import { cardVariants, dur, ease, press, spring } from "../lib/motion";
import { haptic, openExternal } from "../lib/telegram";
import type { Product } from "../lib/types";
import { Arch, CountUp, Photo, Stamp } from "./archive";
import { IconHeart, IconPriceDown } from "./icons";
import { cx } from "./ui";

type View = "grid" | "list";
type Extra = {
  /** Position in the result list: drives the cascade delay and the inventory number. */
  index?: number;
  /** Same listing already shown above (dedup on the client). */
  duplicate?: boolean;
  /** ULTRA price alerts: price at the moment of saving (Favorite.saved_price). */
  previousPrice?: string | null;
  previousCurrency?: string | null;
  /** "arch": exhibit card with a pointed-arch top — used in the collection. */
  frame?: "rounded" | "arch";
};

const dotColor = (v: number) => (v >= 75 ? "#7CE3A6" : v >= 45 ? "#F5F3EE" : "#A6A6A6");

/** Similarity badge — rendered only when the model produced a number; no reserved space otherwise. */
function Similarity({ value, delay, small }: { value: number; delay: number; small?: boolean }) {
  return (
    <span title="Визуальное сходство, рассчитанное моделью"
      className={cx("inline-flex items-center gap-1.5 rounded-full bg-black/60 font-mono font-medium text-[#F5F3EE] backdrop-blur",
        small ? "h-5 px-1.5 text-[10px]" : "h-6 px-2 text-[11px]")}>
      <span className={cx("rounded-full", small ? "h-[5px] w-[5px]" : "h-1.5 w-1.5")} style={{ background: dotColor(value) }} />
      <CountUp value={value} duration={0.7} delay={delay} suffix="%" />
    </span>
  );
}

const ANGLES = [0, 45, 90, 135, 180, 225, 270, 315];
/** Heart: bouncy pop + 8 accent particles on add (choreography VI). */
function Heart({ on, onToggle, variant }: { on: boolean; onToggle: (v: boolean) => void; variant: "photo" | "plain" }) {
  const [burst, setBurst] = useState(0);
  const reduce = useReducedMotion();
  return (
    <motion.button type="button" aria-label={on ? "Убрать из избранного" : "В избранное"} aria-pressed={on}
      whileTap={{ scale: 0.9 }} transition={spring.bouncy}
      onClick={(e) => {
        e.stopPropagation();
        const next = !on;
        if (next) { haptic.tap(); setBurst((b) => b + 1); } else haptic.select();
        onToggle(next);
      }}
      className={cx("relative grid h-9 w-9 place-items-center rounded-full transition-colors",
        on ? "bg-accent text-white" : variant === "photo" ? "bg-black/40 text-white backdrop-blur-md" : "bg-transparent text-ink-2")}>
      <motion.span key={burst} className="grid" initial={burst && !reduce ? { scale: 1 } : false} animate={{ scale: [1, 1.25, 1] }} transition={spring.bouncy}>
        <IconHeart size={17} filled={on} />
      </motion.span>
      <AnimatePresence>
        {burst > 0 && !reduce && on && (
          <motion.span key={burst} className="pointer-events-none absolute inset-0" initial={{ opacity: 1 }} animate={{ opacity: 0 }}
            transition={{ duration: 0.42, ease: ease.outExpo }}>
            {ANGLES.map((a) => (
              <motion.span key={a} className="absolute top-1/2 left-1/2 -mt-[2.5px] -ml-[2.5px] h-[5px] w-[5px] rounded-full bg-accent"
                initial={{ x: 0, y: 0 }}
                animate={{ x: Math.sin((a * Math.PI) / 180) * 22, y: -Math.cos((a * Math.PI) / 180) * 22 }}
                transition={{ duration: 0.42, ease: ease.outExpo }} />
            ))}
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

function inventoryLine(p: Product, index: number | undefined, duplicate?: boolean): string {
  const no = `№ ${String(index !== undefined ? index + 1 : p.product_id % 10000).padStart(4, "0")}`;
  const parts = [no];
  if (duplicate) parts.push("Дубль");
  if (p.via === "google_lens") parts.push("По фото в Google");
  else if (p.via === "web_search") parts.push("Веб-поиск");
  if (p.condition) parts.push(CONDITION_LABEL[p.condition] ?? p.condition);
  if (p.available === true) parts.push("В наличии");
  if (p.available === false) parts.push("Нет в наличии");
  return parts.join(" · ");
}

function Price({ p, previousPrice, previousCurrency }: { p: Product } & Pick<Extra, "previousPrice" | "previousCurrency">) {
  if (p.price === null) {
    return <span className="font-serif text-[17px] font-normal text-ink-2 italic">Цена на сайте</span>;
  }
  const dropped = previousPrice != null && Number(previousPrice) > Number(p.price);
  return (
    <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
      {dropped && <IconPriceDown size={13} strokeWidth={2} className="self-center text-good" aria-label="Цена снизилась" />}
      <span className="font-mono text-[17px] font-semibold tracking-[-0.01em] tnum">{money(p.price, p.currency)}</span>
      {dropped && <span className="font-mono text-[12px] text-ink-3 line-through tnum">{money(previousPrice, previousCurrency ?? p.currency)}</span>}
      {p.price_converted && p.converted_currency !== p.currency && (
        <span className="font-mono text-[12px] text-ink-3 tnum">≈ {money(p.price_converted, p.converted_currency)}</span>
      )}
    </div>
  );
}

export function ProductCard({ p, view, onFavorite, index, duplicate, previousPrice, previousCurrency, frame = "rounded" }:
  { p: Product; view: View; onFavorite: (on: boolean) => void } & Extra) {
  const gone = p.available === false;
  const delay = index !== undefined && index < 10 ? index * 0.04 : 0;
  const stamp = gone ? "Снято" : p.marketplace_name;
  const inv = inventoryLine(p, index, duplicate);
  const common = {
    layout: true as const,
    custom: index ?? 0,
    variants: cardVariants,
    initial: "hidden",
    animate: "show",
    whileTap: { scale: press.card },
    transition: spring.soft,
    onClick: () => openExternal(p.url),
  };

  if (view === "list") {
    return (
      <motion.article {...common}
        className={cx("relative flex cursor-pointer gap-3.5 border-b border-line py-3.5", duplicate && "opacity-60")}>
        <motion.div layoutId={`thumb-${p.product_id}`} className="relative h-[110px] w-[88px] shrink-0 overflow-hidden rounded-xl shadow-[inset_0_0_0_1px_var(--line)]">
          <Photo src={p.image_url} fallback={p.image_fallback_url} alt={p.title} grayscale={gone} />
          {p.similarity !== null && <div className="absolute bottom-1.5 left-1.5"><Similarity value={p.similarity} delay={delay} small /></div>}
        </motion.div>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5 pr-10">
          <motion.div layout="position"><Stamp muted={gone}>{stamp}</Stamp></motion.div>
          <motion.h3 layout="position" className="line-clamp-2 text-[14px] leading-[19px]">{p.title}</motion.h3>
          <motion.p layout="position" className="inv">{inv}</motion.p>
          <motion.div layout="position" className="mt-auto flex justify-end"><Price p={p} previousPrice={previousPrice} previousCurrency={previousCurrency} /></motion.div>
        </div>
        <div className="absolute top-2.5 right-0"><Heart on={p.is_favorite} onToggle={onFavorite} variant="plain" /></div>
      </motion.article>
    );
  }

  return (
    <motion.article {...common} className={cx("flex cursor-pointer flex-col gap-2", duplicate && "opacity-60", gone && "opacity-85")}>
      <motion.div layoutId={`thumb-${p.product_id}`}
        className={cx("relative aspect-[4/5]", frame === "rounded" && "overflow-hidden rounded-[18px] bg-surface-2 shadow-[inset_0_0_0_1px_var(--line)]")}>
        {frame === "arch"
          ? <Arch className="absolute inset-0"><Photo src={p.image_url} fallback={p.image_fallback_url} alt={p.title} grayscale={gone} /></Arch>
          : <Photo src={p.image_url} fallback={p.image_fallback_url} alt={p.title} grayscale={gone} />}
        {frame === "rounded" && (p.image_url || p.image_fallback_url) && <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent from-60% to-black/35" />}
        {frame === "rounded" ? (
          <>
            <div className="absolute top-2.5 left-2.5"><Stamp onPhoto className="bg-black/25 backdrop-blur-[6px]">{stamp}</Stamp></div>
            <div className="absolute top-2 right-2"><Heart on={p.is_favorite} onToggle={onFavorite} variant="photo" /></div>
            {p.similarity !== null && <div className="absolute bottom-2.5 left-2.5"><Similarity value={p.similarity} delay={delay} /></div>}
          </>
        ) : (
          /* Arch top is too narrow for corner badges: stamp and heart sit on the base of the exhibit. */
          <>
            <div className="absolute bottom-2.5 left-2.5"><Stamp onPhoto className="bg-black/25 backdrop-blur-[6px]">{stamp}</Stamp></div>
            <div className="absolute right-2 bottom-2"><Heart on={p.is_favorite} onToggle={onFavorite} variant="photo" /></div>
          </>
        )}
      </motion.div>
      <motion.p layout="position" className="inv">{inv}</motion.p>
      <motion.h3 layout="position" className="line-clamp-2 min-h-[38px] text-[14px] leading-[19px]">{p.title}</motion.h3>
      <motion.div layout="position"><Price p={p} previousPrice={previousPrice} previousCurrency={previousCurrency} /></motion.div>
    </motion.article>
  );
}

export function ProductSkeleton({ view }: { view: View }) {
  if (view === "list") {
    return (
      <div className="flex gap-3.5 border-b border-line py-3.5">
        <div className="shimmer h-[110px] w-[88px] rounded-xl" />
        <div className="flex-1 space-y-2.5 py-1"><div className="shimmer h-[18px] w-16" /><div className="shimmer h-3.5 w-5/6" /><div className="shimmer h-2.5 w-1/2" /></div>
      </div>
    );
  }
  return (
    <motion.div className="flex flex-col gap-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: dur.element }}>
      <div className="shimmer aspect-[4/5] rounded-[18px]" />
      <div className="shimmer h-2.5 w-3/5" /><div className="shimmer h-3.5 w-full" /><div className="shimmer h-4 w-2/5" />
    </motion.div>
  );
}
