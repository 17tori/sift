import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { spring } from "../lib/motion";
import { useMe, useWatches, useWatchToggle } from "../lib/queries";
import { haptic } from "../lib/telegram";
import { toast } from "../lib/toast";
import { IconBell, IconLock } from "./icons";
import { cx } from "./ui";

/** «Сообщить, когда появится дешевле или на новой площадке» (ULTRA). The bell rings when switched on. */
export function WatchButton({ searchId, watching: known, compact }: { searchId: string; watching?: boolean; compact?: boolean }) {
  const { data: me } = useMe();
  const watches = useWatches();
  const toggle = useWatchToggle();
  const nav = useNavigate();
  const reduce = useReducedMotion();
  const [ring, setRing] = useState(0);
  const limit = me?.plan.features.watch_limit ?? 0;
  const watching = known ?? !!watches.data?.items.some((w) => w.search_id === searchId);
  const locked = limit <= 0;
  const click = () => {
    if (locked) { haptic.select(); nav("/subscription"); return; }
    const on = !watching;
    toggle.mutate({ searchId, on }, {
      onSuccess: () => {
        if (on) { setRing((r) => r + 1); haptic.success(); toast("Слежу. Напишу в чат, когда найдётся дешевле или на новой площадке", "good"); }
        else { haptic.select(); toast("Больше не слежу за этой вещью"); }
      },
      onError: (e) => { haptic.error(); toast(e instanceof ApiError ? e.message : "Не получилось", "bad"); },
    });
  };
  return (
    <motion.button type="button" onClick={click} whileTap={{ scale: 0.97 }} transition={spring.bouncy} disabled={toggle.isPending}
      aria-pressed={watching}
      className={cx("relative inline-flex items-center gap-2 rounded-full text-[13px] font-medium transition-colors",
        compact ? "h-[34px] px-3" : "h-10 px-4",
        watching ? "bg-ink text-bg" : "text-ink shadow-[inset_0_0_0_1px_var(--line-strong)]")}>
      {watching && !reduce && (
        <motion.span aria-hidden className="absolute inset-0 rounded-full shadow-[0_0_0_1px_var(--accent)]"
          animate={{ scale: [1, 1.12], opacity: [0.7, 0] }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }} />
      )}
      <motion.span key={ring} className="grid origin-top" initial={false}
        animate={ring && !reduce ? { rotate: [0, -18, 14, -10, 6, 0] } : {}} transition={{ duration: 0.7 }}>
        {locked ? <IconLock size={15} /> : <IconBell size={15} filled={watching} />}
      </motion.span>
      {watching ? "Слежу за вещью" : "Следить за ценой"}
      {locked && <span className="font-mono text-[10px] tracking-[0.1em] text-ink-3">ULTRA</span>}
    </motion.button>
  );
}
