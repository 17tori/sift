import { motion, useReducedMotion } from "motion/react";
import { useMemo, useRef, useState } from "react";
import { date, money } from "../lib/format";
import { ease } from "../lib/motion";
import type { PricePoint } from "../lib/types";

/** Price history of one listing: 2 px line drawn in, crosshair + value on touch. One series, no legend. */
export function Sparkline({ points, height = 96 }: { points: PricePoint[]; height?: number }) {
  const reduce = useReducedMotion();
  const ref = useRef<SVGSVGElement>(null);
  const [hi, setHi] = useState<number | null>(null);
  const W = 320;
  const data = useMemo(() => {
    const cur = points[points.length - 1]?.currency;
    return points.filter((p) => p.currency === cur).map((p) => ({ v: Number(p.price), t: new Date(p.at).getTime(), p }));
  }, [points]);
  if (data.length < 2) return null;
  const vs = data.map((d) => d.v);
  const lo = Math.min(...vs), hiV = Math.max(...vs);
  const t0 = data[0].t, t1 = data[data.length - 1].t;
  const pad = 8;
  const x = (t: number) => (t1 === t0 ? W / 2 : pad + ((t - t0) / (t1 - t0)) * (W - pad * 2));
  const y = (v: number) => (hiV === lo ? height / 2 : pad + (1 - (v - lo) / (hiV - lo)) * (height - pad * 2));
  // step line: a price holds until the next observation
  let d = `M${x(data[0].t)},${y(data[0].v)}`;
  for (let i = 1; i < data.length; i++) d += ` H${x(data[i].t)} V${y(data[i].v)}`;
  const last = data[data.length - 1];
  const sel = hi !== null ? data[hi] : last;
  const move = (clientX: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const px = ((clientX - r.left) / r.width) * W;
    let best = 0;
    data.forEach((q, i) => { if (Math.abs(x(q.t) - px) < Math.abs(x(data[best].t) - px)) best = i; });
    setHi(best);
  };
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-[15px] font-semibold tnum">{money(sel.v, sel.p.currency)}</span>
        <span className="caption text-ink-3">{date(sel.p.at)}</span>
      </div>
      <svg ref={ref} viewBox={`0 0 ${W} ${height}`} className="mt-2 w-full touch-none text-ink" style={{ height }}
        onPointerMove={(e) => move(e.clientX)} onPointerDown={(e) => move(e.clientX)} onPointerLeave={() => setHi(null)}
        role="img" aria-label={`История цены: от ${money(lo, last.p.currency)} до ${money(hiV, last.p.currency)}`}>
        <line x1={0} x2={W} y1={y(lo)} y2={y(lo)} stroke="var(--line)" strokeDasharray="2 4" />
        <line x1={0} x2={W} y1={y(hiV)} y2={y(hiV)} stroke="var(--line)" strokeDasharray="2 4" />
        <motion.path d={d} fill="none" stroke="currentColor" strokeWidth={2} strokeLinejoin="round" vectorEffect="non-scaling-stroke"
          initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: ease.ritual }} />
        {hi !== null && <line x1={x(sel.t)} x2={x(sel.t)} y1={0} y2={height} stroke="var(--line-strong)" />}
        <motion.circle cx={x(sel.t)} cy={y(sel.v)} r={4.5} fill="var(--accent)" stroke="var(--bg)" strokeWidth={2}
          initial={reduce ? false : { scale: 0 }} animate={{ scale: 1 }} transition={{ delay: hi === null ? 1 : 0, duration: 0.2 }} />
      </svg>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-3 tnum">
        <span>мин {money(lo, last.p.currency)}</span><span>макс {money(hiV, last.p.currency)}</span>
      </div>
    </div>
  );
}
