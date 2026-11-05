import { AnimatePresence, motion } from "motion/react";
import { spring } from "../lib/motion";
import { useToast } from "../lib/toast";
import { cx } from "./ui";

/** Bottom toasts above the tab bar: spring up, fade down. */
export function Toaster() {
  const { items, drop } = useToast();
  return (
    <div className="pointer-events-none fixed inset-x-0 z-[60] flex flex-col items-center gap-2 px-5"
      style={{ bottom: "calc(92px + var(--tg-safe-bottom, 0px))" }} aria-live="polite">
      <AnimatePresence initial={false}>
        {items.map((t) => (
          <motion.button key={t.id} layout onClick={() => drop(t.id)}
            initial={{ opacity: 0, y: 24, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={spring.soft}
            className={cx("pointer-events-auto max-w-sm rounded-[14px] bg-ink px-4 py-3 text-left text-[14px] leading-[19px] text-bg shadow-lg",
              t.tone === "bad" && "bg-bad text-white")}>
            {t.tone === "good" && <span className="mr-2 inline-block h-1.5 w-1.5 -translate-y-px rounded-full bg-accent align-middle" />}
            {t.text}
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}
