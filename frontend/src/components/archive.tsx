/* Gothic-archive layer: arch mask, ornament, rosette, provenance stamp, ledger row, count-up. Inline SVG, currentColor. */
import { animate, motion, useInView, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { ARCH_PATH, RECT_PATH, breathe, dur, ease, spring, stagger } from "../lib/motion";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/** Stroke path of the arch in a 0..100 box, for the 1 px outline overlay. */
const ARCH_STROKE = "M.5,100 L.5,42 C.5,18 26,4 50,.5 C74,4 99.5,18 99.5,42 L99.5,100 Z";

/**
 * Pointed-arch mask. Children are clipped; a 1 px outline is drawn on top.
 * `morph` animates the mask from rectangle to arch (choreography II).
 */
export function Arch({ children, className, outline = true, dashed, morph, outlineClass = "text-line-strong" }: {
  children?: ReactNode; className?: string; outline?: boolean; dashed?: boolean; morph?: boolean; outlineClass?: string;
}) {
  const id = useId().replace(/:/g, "");
  const reduce = useReducedMotion();
  return (
    <div className={cx("relative", className)}>
      <svg width="0" height="0" className="absolute" aria-hidden>
        <defs>
          <clipPath id={`arch-${id}`} clipPathUnits="objectBoundingBox">
            {morph && !reduce
              ? <motion.path initial={{ d: RECT_PATH }} animate={{ d: ARCH_PATH }} transition={{ duration: dur.screen, ease: ease.inOut }} />
              : <path d={ARCH_PATH} />}
          </clipPath>
        </defs>
      </svg>
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `url(#arch-${id})` }}>{children}</div>
      {outline && (
        <svg className={cx("pointer-events-none absolute inset-0 h-full w-full", outlineClass)} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          <path d={ARCH_STROKE} fill="none" stroke="currentColor" strokeWidth={dashed ? 1.25 : 1} strokeDasharray={dashed ? "5 7" : undefined}
            vectorEffect="non-scaling-stroke" />
        </svg>
      )}
    </div>
  );
}

/** Photo inside an arch, with shimmer → reveal (opacity 0→1, scale 1.03→1). */
export function ArchImage({ src, alt, className, morph }: { src: string | null; alt: string; className?: string; morph?: boolean }) {
  return (
    <Arch className={className} morph={morph}>
      <Photo src={src} alt={alt} />
    </Arch>
  );
}

/** Image with fallback chain, shimmer while loading and the 500 ms reveal. */
export function Photo({ src, fallback, alt, className, grayscale }: {
  src: string | null; fallback?: string | null; alt: string; className?: string; grayscale?: boolean;
}) {
  const list = [src, fallback].filter((u): u is string => !!u);
  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const cur = list[idx];
  if (!cur) return <PhotoMissing />;
  return (
    <div className={cx("relative h-full w-full bg-surface-2", className)}>
      <motion.img key={cur} src={cur} alt={alt} loading="lazy" decoding="async" referrerPolicy="no-referrer"
        onLoad={() => setLoaded(true)} onError={() => { setLoaded(false); setIdx((i) => i + 1); }}
        initial={{ opacity: 0, scale: 1.03 }} animate={loaded ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 1.03 }}
        transition={{ duration: dur.photo, ease: ease.outExpo }}
        className={cx("h-full w-full object-cover", grayscale && "grayscale-[.6]")} />
      {!loaded && <div className="shimmer absolute inset-0" />}
    </div>
  );
}

export function PhotoMissing() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2.5 bg-surface-2 text-ink-3">
      <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.25} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 7a2 2 0 1 1 2-2M12 7v2L3.5 15.5A1 1 0 0 0 4.1 17.3h15.8a1 1 0 0 0 .6-1.8L12 9" />
      </svg>
      <span className="inv">Фото недоступно</span>
    </div>
  );
}

/** Line — diamond — line. `draw` strokes it out from the centre (choreography I). */
export function Ornament({ className, draw }: { className?: string; draw?: boolean }) {
  const reduce = useReducedMotion();
  const anim = draw && !reduce;
  return (
    <div className={cx("flex items-center gap-2.5", className)} aria-hidden>
      <motion.span className="h-px flex-1 origin-right bg-current" initial={anim ? { scaleX: 0 } : false} animate={{ scaleX: 1 }}
        transition={{ duration: 0.56, delay: 0.18, ease: ease.outExpo }} />
      <svg width="9" height="9" viewBox="0 0 9 9"><path d="M4.5 .7 8.3 4.5 4.5 8.3 .7 4.5Z" fill="none" stroke="currentColor" /></svg>
      <motion.span className="h-px flex-1 origin-left bg-current" initial={anim ? { scaleX: 0 } : false} animate={{ scaleX: 1 }}
        transition={{ duration: 0.56, delay: 0.18, ease: ease.outExpo }} />
    </div>
  );
}

/** Section header: Roman numeral (Cormorant) + mono label + hairline drawn left→right. */
export function SectionMark({ numeral, label, right, className }: { numeral?: string; label: string; right?: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true });
  return (
    <div ref={ref} className={cx("flex items-center gap-3", className)}>
      {numeral && <span className="font-serif text-[22px] leading-none font-light">{numeral}</span>}
      <span className="caption text-ink-2">{numeral ? "— " : ""}{label}</span>
      <motion.span className="h-px flex-1 origin-left bg-line-strong" initial={{ scaleX: 0 }} animate={inView ? { scaleX: 1 } : {}}
        transition={{ duration: dur.screen, ease: ease.outExpo }} />
      {right}
    </div>
  );
}

const PETAL = "M50 8 C59 26 59 38 50 50 C41 38 41 26 50 8 Z";
/** Gothic rosette for empty states and splash. `breathing`: opacity .6 ↔ 1 over 4 s. */
export function Rosette({ size = 132, className, breathing, strokeWidth = 0.9 }: { size?: number; className?: string; breathing?: boolean; strokeWidth?: number }) {
  const reduce = useReducedMotion();
  return (
    <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
      className={className} aria-hidden {...(breathing && !reduce ? breathe : {})}>
      <circle cx="50" cy="50" r="46" /><circle cx="50" cy="50" r="42" /><circle cx="50" cy="50" r="13" /><circle cx="50" cy="50" r="3" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => <path key={a} d={PETAL} transform={`rotate(${a} 50 50)`} />)}
    </motion.svg>
  );
}

/**
 * Provenance stamp: marketplace name in mono caps inside a thin relic frame.
 * `onPhoto` switches to Ivory 70 % for dark photos. `land` plays the seal animation once (choreography IV).
 */
export function Stamp({ children, onPhoto, land, muted, className }: { children: ReactNode; onPhoto?: boolean; land?: boolean; muted?: boolean; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.span
      initial={land && !reduce ? { scale: 1.15, rotate: -2, opacity: 0 } : false}
      animate={{ scale: 1, rotate: 0, opacity: 1 }} transition={spring.bouncy}
      className={cx("inline-flex h-[18px] items-center border px-1.5 font-mono text-[10px] leading-none tracking-[0.12em] uppercase",
        onPhoto ? "border-[rgba(245,243,238,.7)] text-[#F5F3EE]" : muted ? "border-line text-ink-3" : "border-relic text-relic-ink", className)}>
      {children}
    </motion.span>
  );
}

/** Ledger row: mono caps key / value, hairline below. `typewriter` prints the value char by char. */
export function LedgerRow({ k, v, index = 0, typewriter, children }: { k: string; v?: string; index?: number; typewriter?: boolean; children?: ReactNode }) {
  return (
    <motion.div className="flex items-center justify-between gap-3 border-b border-line py-2.5"
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: dur.element, ease: ease.outExpo, delay: index * stagger.ledger }}>
      <span className="caption text-ink-3">{k}</span>
      {children ?? <span className="caption text-right text-ink">{typewriter && v ? <Typewriter text={v} delay={index * stagger.ledger} /> : v}</span>}
    </motion.div>
  );
}

export function Typewriter({ text, delay = 0 }: { text: string; delay?: number }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? text.length : 0);
  useEffect(() => {
    if (reduce) { setN(text.length); return; }
    setN(0);
    let i = 0;
    let timer: number | undefined;
    const start = window.setTimeout(() => {
      timer = window.setInterval(() => { i += 1; setN(i); if (i >= text.length) window.clearInterval(timer); }, stagger.typewriterChar * 1000);
    }, delay * 1000);
    return () => { window.clearTimeout(start); window.clearInterval(timer); };
  }, [text, delay, reduce]);
  return <>{text.slice(0, n)}</>;
}

/** Board-style count-up (choreographies IV, V). */
export function CountUp({ value, from = 0, duration = 0.6, delay = 0, suffix = "", className }: {
  value: number; from?: number; duration?: number; delay?: number; suffix?: string; className?: string;
}) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? value : from);
  const text = useTransform(mv, (x) => `${new Intl.NumberFormat("ru-RU").format(Math.round(x))}${suffix}`);
  useEffect(() => {
    if (reduce) { mv.set(value); return; }
    const c = animate(mv, value, { duration, delay, ease: ease.outExpo });
    return () => c.stop();
  }, [value, duration, delay, reduce, mv]);
  return <motion.span className={cx("tnum", className)}>{text}</motion.span>;
}

/** Wordmark in blackletter (Latin only) or the Cormorant caps fallback with an arch over the I. */
export function Wordmark({ variant = "blackletter", size = 30, className }: { variant?: "blackletter" | "serif"; size?: number; className?: string }) {
  if (variant === "blackletter") {
    return <span className={cx("font-blackletter leading-none", className)} style={{ fontSize: size }}>Sift</span>;
  }
  return (
    <span className={cx("inline-flex items-end font-serif leading-none tracking-[0.18em]", className)} style={{ fontSize: size }}>
      S
      <span className="inline-flex flex-col items-center">
        <svg width={size * 0.26} height={size * 0.21} viewBox="0 0 22 18" aria-hidden>
          <path d="M1 17 C1 8 6 3 11 1 C16 3 21 8 21 17" fill="none" stroke="currentColor" strokeWidth="1.25" />
        </svg>
        I
      </span>
      FT
    </span>
  );
}
