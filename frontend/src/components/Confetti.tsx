import { motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";
import { ease } from "../lib/motion";

/** Archival confetti: diamonds, hairline bars and stars thrown out of one point, then falling. */
export function Confetti({ count = 26, spread = 150, className }: { count?: number; spread?: number; className?: string }) {
  const reduce = useReducedMotion();
  const bits = useMemo(() => Array.from({ length: count }, (_, i) => {
    const a = (i / count) * Math.PI * 2 + (Math.random() - 0.5) * 0.5;
    const r = spread * (0.55 + Math.random() * 0.45);
    return {
      i,
      x: Math.cos(a) * r,
      y: Math.sin(a) * r * 0.7 - 30,
      fall: 60 + Math.random() * 90,
      rot: (Math.random() - 0.5) * 540,
      kind: i % 3,
      color: ["var(--accent)", "var(--relic)", "var(--ink)"][i % 3],
      delay: Math.random() * 0.12,
      size: 5 + Math.random() * 5,
    };
  }), [count, spread]);
  if (reduce) return null;
  return (
    <div className={"pointer-events-none absolute top-1/2 left-1/2 " + (className ?? "")} aria-hidden>
      {bits.map((b) => (
        <motion.span key={b.i} className="absolute block"
          style={{ width: b.kind === 1 ? 2 : b.size, height: b.kind === 1 ? b.size * 2 : b.size, background: b.kind === 2 ? "none" : b.color, color: b.color,
            rotate: b.kind === 0 ? 45 : 0 }}
          initial={{ x: 0, y: 0, opacity: 0, scale: 0.4 }}
          animate={{ x: b.x, y: [0, b.y, b.y + b.fall], opacity: [0, 1, 0], scale: 1, rotate: b.rot }}
          transition={{ duration: 1.5, delay: b.delay, ease: ease.outExpo, times: [0, 0.35, 1] }}>
          {b.kind === 2 && (
            <svg width={b.size + 3} height={b.size + 3} viewBox="0 0 10 10"><path d="M5 0 6.2 3.8 10 5 6.2 6.2 5 10 3.8 6.2 0 5 3.8 3.8Z" fill="currentColor" /></svg>
          )}
        </motion.span>
      ))}
    </div>
  );
}
