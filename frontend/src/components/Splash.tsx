import { motion, useReducedMotion } from "motion/react";
import { dur, ease, t } from "../lib/motion";
import { useEffect, useState } from "react";
import { Ornament } from "./archive";
import { Sieve, sieveRiseDuration } from "./Sieve";

const COLS = 15;

/**
 * I. Splash: the sieve fills row by row from its base, the blue dot lights up, then the SIFT word and the
 * slogan appear; the screen leaves upward. Mount inside <AnimatePresence> so the exit plays.
 */
export function Splash() {
  const reduce = useReducedMotion();
  const after = reduce ? 0 : sieveRiseDuration(0.1);
  return (
    <motion.div className="fixed inset-0 z-[70] flex flex-col items-center justify-center overflow-hidden bg-bg px-10 pb-[6vh] text-ink"
      exit={reduce ? { opacity: 0, transition: t.reduced } : { y: "-100%", transition: { duration: dur.screen, ease: ease.inOut } }}>
      <span className="caption absolute top-[calc(env(safe-area-inset-top)+28px)] text-ink-3">Архив № I · визуальный поиск</span>
      <Sieve cols={COLS} width={132} animate="rise" delay={0.1} title="SIFT" />
      <motion.span className="mt-9 font-serif text-[52px] leading-none tracking-[0.2em] [margin-right:-0.2em]"
        initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: ease.ritual, delay: after }}>
        SIFT
      </motion.span>
      {/* key on the delay: the ornament mounts (and strokes out) only once the word is in */}
      <motion.div className="mt-6 w-[180px] text-relic" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }}
        transition={{ duration: 0.01, delay: after + 0.2 }}>
        <DelayedOrnament after={reduce ? 0 : after + 0.2} />
      </motion.div>
      <motion.p className="mt-6 text-center font-serif text-[26px] leading-[30px] font-light"
        initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }}
        transition={{ duration: dur.screen, delay: after + 0.25, ease: ease.outExpo }}>
        Одна фотография.<br /><i>Все</i> маркетплейсы.
      </motion.p>
    </motion.div>
  );
}

function DelayedOrnament({ after }: { after: number }) {
  const [show, setShow] = useState(after === 0);
  useEffect(() => {
    if (after === 0) return;
    const id = window.setTimeout(() => setShow(true), after * 1000);
    return () => window.clearTimeout(id);
  }, [after]);
  return show ? <Ornament draw /> : <div className="h-[9px]" />;
}
