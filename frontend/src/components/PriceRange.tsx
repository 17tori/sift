import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { money } from "../lib/format";
import { ease, spring } from "../lib/motion";
import { cmp } from "../lib/price";
import type { PriceRange as Range, Product } from "../lib/types";
import { SectionMark } from "./archive";
import { cx } from "./ui";

/**
 * The same item across marketplaces as dots on one price axis. Single measure, single axis.
 * Cheapest dot carries the accent; every dot is a tap target that names its marketplace and price.
 */
export function PriceAxis({ offers, current, onPick }: { offers: Product[]; current?: number; onPick?: (p: Product) => void }) {
  const reduce = useReducedMotion();
  const pts = offers.map((p) => ({ p, c: cmp(p) })).filter((x): x is { p: Product; c: NonNullable<ReturnType<typeof cmp>> } => !!x.c);
  const [hover, setHover] = useState<number | null>(null);
  if (pts.length < 2) return null;
  const cur = pts[0].c.currency;
  const same = pts.filter((x) => x.c.currency === cur);
  const lo = Math.min(...same.map((x) => x.c.value));
  const hi = Math.max(...same.map((x) => x.c.value));
  const pos = (v: number) => (hi === lo ? 50 : 4 + ((v - lo) / (hi - lo)) * 92);
  const shown = hover !== null ? same.find((x) => x.p.product_id === hover) : null;
  return (
    <div className="relative pt-7 pb-1">
      {/* tooltip */}
      <div className="absolute inset-x-0 top-0 h-6">
        {shown && (
          <motion.div key={shown.p.product_id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}
            className="absolute -translate-x-1/2 rounded-[4px] bg-ink px-2 py-1 font-mono text-[11px] whitespace-nowrap text-bg"
            style={{ left: `clamp(60px, ${pos(shown.c.value)}%, calc(100% - 60px))` }}>
            {shown.p.marketplace_name} · {money(shown.c.value, shown.c.currency)}
          </motion.div>
        )}
      </div>
      <div className="relative h-6">
        <motion.div className="absolute top-1/2 right-0 left-0 h-px origin-left bg-line-strong" initial={reduce ? false : { scaleX: 0 }} animate={{ scaleX: 1 }}
          transition={{ duration: 0.7, ease: ease.outExpo }} />
        <motion.div className="absolute top-1/2 h-[3px] -translate-y-1/2 origin-left rounded-full bg-ink"
          style={{ left: `${pos(lo)}%`, width: `${pos(hi) - pos(lo)}%` }}
          initial={reduce ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, delay: 0.15, ease: ease.outExpo }} />
        {same.map((x, i) => {
          const cheapest = x.c.value === lo;
          const isCur = x.p.product_id === current;
          return (
            <motion.button key={x.p.product_id} type="button" aria-label={`${x.p.marketplace_name}: ${money(x.c.value, x.c.currency)}`}
              className="absolute top-1/2 -mt-[14px] -ml-[14px] grid h-7 w-7 place-items-center"
              style={{ left: `${pos(x.c.value)}%` }}
              initial={reduce ? false : { scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              transition={{ ...spring.bouncy, delay: 0.35 + i * 0.07 }}
              onPointerEnter={() => setHover(x.p.product_id)} onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(x.p.product_id)} onBlur={() => setHover(null)}
              onClick={() => { setHover(x.p.product_id); onPick?.(x.p); }}>
              <span className={cx("block rounded-full ring-2 ring-bg", cheapest ? "h-3 w-3 bg-accent" : "h-2.5 w-2.5 bg-ink",
                isCur && "outline-1 outline-offset-2 outline-ink")} />
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

/** «от 2 400 ₽ на Avito до 6 900 ₽ на eBay» — shown above the results when the same item is on 2+ marketplaces. */
export function PriceSummary({ range, onOpen }: { range: Range; onOpen: (p: Product) => void }) {
  const a = cmp(range.min);
  const b = cmp(range.max);
  if (!a || !b) return null;
  const save = b.value - a.value;
  const pct = b.value > 0 ? Math.round((save / b.value) * 100) : 0;
  return (
    <motion.div className="mt-6" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.42, ease: ease.outExpo }}>
      <SectionMark label="Та же вещь · сверено по фото" />
      <p className="mt-3 font-serif text-[26px] leading-[30px] font-light">
        от <button className="font-mono text-[21px] font-semibold tracking-[-0.02em] text-accent underline-offset-4 active:underline tnum" onClick={() => onOpen(range.min)}>{money(a.value, a.currency)}</button>
        {" "}на <i className="font-normal">{range.min.marketplace_name}</i>{" "}
        до <button className="font-mono text-[21px] font-semibold tracking-[-0.02em] tnum" onClick={() => onOpen(range.max)}>{money(b.value, b.currency)}</button>
        {" "}на <i className="font-normal">{range.max.marketplace_name}</i>
      </p>
      <PriceAxis offers={[range.min, range.max]} onPick={onOpen} />
      <p className="caption mt-1 text-ink-3">
        {range.count} предл. на {range.marketplaces} площадках{pct >= 5 ? <> · <span className="text-ink">разница {money(save, a.currency)} ({pct}%)</span></> : null}
      </p>
    </motion.div>
  );
}
