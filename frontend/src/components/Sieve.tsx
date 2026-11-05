import { motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";
import { dur, ease } from "../lib/motion";

/**
 * The SIFT mark: a sieve of dots inside a pointed arch, one cell lit in Electric blue — the item found.
 * Built in code so it stays sharp at any size: 9–11 columns for small sizes, 15+ for large ones.
 * Dots near the arch shrink with their distance to the outline, which draws the arch without a line.
 */

type Cell = readonly [row: number, col: number];

export type SieveProps = {
  cols?: number;
  /** Lit cell as [row, col] from the top-left, or null for none ("nothing found"). Default: lower right of centre. */
  accent?: Cell | null;
  /** Rendered width in px; height follows the mark's proportions. */
  width?: number;
  /** "rise": rows appear from the base up, then the blue dot lights. "breathe": slow opacity loop (empty states). */
  animate?: "rise" | "breathe" | false;
  /** Delay before the rise starts, s. */
  delay?: number;
  className?: string;
  title?: string;
};

const PITCH_X = 14;
const PITCH_Y = 14.31;
const R_FULL = 4.1;

type Dot = { x: number; y: number; r: number; row: number; col: number };

const clamp01 = (t: number) => Math.min(1, Math.max(0, t));

export function sieveGeometry(cols: number) {
  const rows = Math.round(cols * 1.45);
  const w = cols * PITCH_X;
  const h = rows * PITCH_Y;
  const a = w / 2; // half width of the arch
  const R = a * 1.14; // radius of each arc of the pointed arch
  const rise = Math.sqrt(R * R - (R - a) * (R - a)); // arch height above the spring line
  const ys = rise - 0.5; // spring line, measured from the top
  const left = (x: number, y: number) => R - Math.hypot(x - (a + (R - a)), y - ys); // arc centred right of middle
  const right = (x: number, y: number) => R - Math.hypot(x - (a - (R - a)), y - ys);
  const dots: Dot[] = [];
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const x = PITCH_X / 2 + col * PITCH_X;
      const y = PITCH_Y / 2 + row * PITCH_Y;
      // signed distance to the outline, positive inside
      const side = Math.min(x, w - x);
      const d = y < ys ? Math.min(side, left(x, y), right(x, y)) : side;
      // falloff fitted to the reference vectors (sift-lockup): full size from half a pitch inside
      const r = R_FULL * clamp01((d + 7.5) / 14.5);
      if (r >= 0.5) dots.push({ x, y, r: Math.round(r * 100) / 100, row, col });
    }
  }
  return { rows, w, h, dots };
}

export function defaultAccent(cols: number): Cell {
  const rows = Math.round(cols * 1.45);
  return [Math.round(rows * 0.69), Math.floor(cols / 2) + 1];
}

export function Sieve({ cols = 11, accent, width = 64, animate = false, delay = 0, className, title }: SieveProps) {
  const reduce = useReducedMotion();
  const { rows, w, h, dots } = useMemo(() => sieveGeometry(cols), [cols]);
  const lit = accent === undefined ? defaultAccent(cols) : accent;
  const litDot = lit ? dots.find((d) => d.row === lit[0] && d.col === lit[1]) : undefined;
  const rising = animate === "rise" && !reduce;
  const rowStep = 0.5 / rows; // whole rise ≈ 0.5 s
  const litAt = delay + rows * rowStep + 0.12;

  return (
    <motion.svg viewBox={`0 0 ${w} ${h}`} width={width} height={(width * h) / w} className={className}
      role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}
      {...(animate === "breathe" && !reduce
        ? { animate: { opacity: [0.6, 1, 0.6] }, transition: { duration: dur.breathe, repeat: Infinity, ease: "easeInOut" } }
        : {})}>
      <g fill="currentColor">
        {dots.map((d) => {
          if (litDot && d === litDot) return null;
          return rising ? (
            <motion.circle key={`${d.row}.${d.col}`} cx={d.x} cy={d.y} r={d.r}
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, ease: ease.outExpo, delay: delay + (rows - 1 - d.row) * rowStep }} />
          ) : (
            <circle key={`${d.row}.${d.col}`} cx={d.x} cy={d.y} r={d.r} />
          );
        })}
      </g>
      {litDot && (
        <motion.g style={{ transformOrigin: `${litDot.x}px ${litDot.y}px`, transformBox: "view-box" }}
          initial={rising ? { opacity: 0, scale: 0.4 } : false} animate={{ opacity: 1, scale: 1 }}
          transition={rising ? { type: "spring", stiffness: 500, damping: 22, delay: litAt } : undefined}>
          <circle cx={litDot.x} cy={litDot.y} r={R_FULL} fill="var(--accent)" />
          <circle cx={litDot.x} cy={litDot.y} r={R_FULL * 2.4} fill="none" stroke="var(--accent)" strokeWidth={1.07} />
        </motion.g>
      )}
    </motion.svg>
  );
}

/** Seconds until the rise finishes and the blue dot is lit — for choreographing what follows. */
export function sieveRiseDuration(delay = 0): number {
  return delay + 0.5 + 0.12 + 0.3; // rows rise in 0.5 s, the dot lights 0.12 s later and settles in ~0.3 s
}
