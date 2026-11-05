import { motion, useReducedMotion } from "motion/react";
import { dur, ease, t, wordmarkReveal } from "../lib/motion";
import { Ornament, Rosette, Wordmark } from "./archive";

/**
 * I. Splash: the wordmark rises through the arch mask, the ornament strokes out from the centre (900 ms),
 * then the screen leaves upward. Mount inside <AnimatePresence> so the exit plays.
 */
export function Splash() {
  const reduce = useReducedMotion();
  return (
    <motion.div className="fixed inset-0 z-[70] flex flex-col items-center overflow-hidden bg-bg px-10 pt-[18vh] pb-14 text-ink"
      exit={reduce ? { opacity: 0, transition: t.reduced } : { y: "-100%", transition: { duration: dur.screen, ease: ease.inOut } }}>
      <Rosette size={560} strokeWidth={0.35} className="pointer-events-none absolute top-[22vh] left-1/2 -translate-x-1/2 opacity-[.06]" />
      <span className="caption text-ink-3">Архив № I · визуальный поиск</span>
      <div className="relative mt-12 flex h-[310px] w-[220px] items-center justify-center">
        <svg className="absolute inset-0 h-full w-full text-line-strong" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          <path d="M.5,100 L.5,42 C.5,18 26,4 50,.5 C74,4 99.5,18 99.5,42 L99.5,100" fill="none" stroke="currentColor" vectorEffect="non-scaling-stroke" />
        </svg>
        <motion.div className="mt-10" {...(reduce ? {} : wordmarkReveal)}><Wordmark size={92} /></motion.div>
      </div>
      <Ornament draw className="mt-7 w-[220px] text-relic" />
      <motion.p className="mt-7 text-center font-serif text-[30px] leading-[34px] font-light"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: dur.screen, delay: 0.5, ease: ease.outExpo }}>
        Одна фотография.<br /><i>Все</i> маркетплейсы.
      </motion.p>
    </motion.div>
  );
}
