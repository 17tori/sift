/* Single-series time chart (line or bar) with crosshair/tooltip. One measure per chart, one axis. */
import { useMemo, useRef, useState } from "react";
import { num } from "../lib/format";

interface Point { date: string; value: number }

const W = 340, H = 150, PAD_L = 30, PAD_R = 8, PAD_T = 10, PAD_B = 22;

function niceMax(v: number): number {
  if (v <= 4) return 4;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

const short = (iso: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" });

export function TimeChart({ title, data, kind = "line", unit = "" }: { title: string; data: Point[]; kind?: "line" | "bar"; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const ref = useRef<SVGSVGElement>(null);
  const total = data.reduce((a, b) => a + b.value, 0);
  const max = niceMax(Math.max(1, ...data.map((d) => d.value)));
  const iw = W - PAD_L - PAD_R, ih = H - PAD_T - PAD_B;
  const step = data.length > 1 ? iw / (data.length - 1) : iw;
  const bw = Math.max(2, iw / data.length - 2);
  const x = (i: number) => (kind === "bar" ? PAD_L + (iw / data.length) * i + 1 : PAD_L + step * i);
  const y = (v: number) => PAD_T + ih - (v / max) * ih;
  const path = useMemo(() => data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join(""), [data, max]); // eslint-disable-line
  const ticks = [0, max / 2, max];
  const labelEvery = Math.ceil(data.length / 5);

  const onMove = (e: React.PointerEvent) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r || !data.length) return;
    const px = ((e.clientX - r.left) / r.width) * W - PAD_L;
    const i = kind === "bar" ? Math.floor(px / (iw / data.length)) : Math.round(px / step);
    setHover(Math.max(0, Math.min(data.length - 1, i)));
  };
  const hp = hover !== null ? data[hover] : null;

  return (
    <div className="rounded-[20px] bg-surface p-4 ring-1 ring-line">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[13px] text-ink-2">{title}</p>
          <p className="font-mono text-2xl font-semibold">{num(hp ? hp.value : total)}{unit && <span className="ml-1 text-base">{unit}</span>}</p>
          <p className="text-[11px] text-ink-3">{hp ? short(hp.date) : `за ${data.length} дн.`}</p>
        </div>
        <button onClick={() => setTable(!table)} className="text-[12px] text-ink-3 underline-offset-2 hover:underline">{table ? "график" : "таблица"}</button>
      </div>
      {table ? (
        <div className="mt-3 max-h-48 overflow-y-auto text-[13px]">
          <table className="w-full"><tbody>
            {[...data].reverse().map((d) => <tr key={d.date} className="border-b border-line"><td className="py-1.5 text-ink-2">{short(d.date)}</td><td className="py-1.5 text-right font-mono">{num(d.value)}</td></tr>)}
          </tbody></table>
        </div>
      ) : (
        <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full touch-none select-none" role="img" aria-label={title}
          onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD_L} x2={W - PAD_R} y1={y(t)} y2={y(t)} stroke="var(--line-strong)" strokeWidth={t === 0 ? 1 : 0.6} strokeDasharray={t === 0 ? "" : "2 4"} />
              <text x={PAD_L - 6} y={y(t) + 3} textAnchor="end" fontSize="9" fill="var(--ink-3)" fontFamily="var(--font-mono)">{num(t)}</text>
            </g>
          ))}
          {data.map((d, i) => i % labelEvery === 0 && (
            <text key={d.date} x={kind === "bar" ? x(i) + bw / 2 : x(i)} y={H - 6} textAnchor="middle" fontSize="9" fill="var(--ink-3)">{short(d.date)}</text>
          ))}
          {kind === "bar" ? data.map((d, i) => {
            const h = Math.max(0, PAD_T + ih - y(d.value));
            const r = Math.min(4, bw / 2, h);
            const x0 = x(i), y0 = y(d.value), yb = PAD_T + ih;
            return (
              <path key={d.date} opacity={hover === null || hover === i ? 1 : 0.45} fill="var(--accent)"
                d={h <= 0 ? "" : `M${x0},${yb}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + bw - r}Q${x0 + bw},${y0} ${x0 + bw},${y0 + r}V${yb}Z`} />
            );
          }) : (
            <>
              <path d={`${path}L${x(data.length - 1)},${PAD_T + ih}L${x(0)},${PAD_T + ih}Z`} fill="var(--accent)" opacity="0.08" />
              <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            </>
          )}
          {hp && hover !== null && (
            <g pointerEvents="none">
              <line x1={kind === "bar" ? x(hover) + bw / 2 : x(hover)} x2={kind === "bar" ? x(hover) + bw / 2 : x(hover)} y1={PAD_T} y2={PAD_T + ih} stroke="var(--ink-3)" strokeWidth="1" />
              {kind === "line" && <circle cx={x(hover)} cy={y(hp.value)} r="4.5" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />}
            </g>
          )}
        </svg>
      )}
    </div>
  );
}
