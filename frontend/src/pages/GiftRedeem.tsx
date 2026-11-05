import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Link, useParams } from "react-router-dom";
import { Arch, CountUp, Ornament } from "../components/archive";
import { Confetti } from "../components/Confetti";
import { IconGift } from "../components/icons";
import { Sieve } from "../components/Sieve";
import { Button } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { plural } from "../lib/format";
import { ease, spring } from "../lib/motion";
import { haptic } from "../lib/telegram";
import type { GiftRedeemOut } from "../lib/types";

/** Opened from t.me/<bot>/app?startapp=g_<code>: a sealed gift the user accepts with one tap. */
export default function GiftRedeem() {
  const { code = "" } = useParams();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api.post<GiftRedeemOut>(`/api/v1/gifts/${encodeURIComponent(code)}/redeem`),
    onSuccess: () => { haptic.success(); qc.invalidateQueries({ queryKey: ["me"] }); },
    onError: () => haptic.error(),
  });
  const r = m.data;
  const own = m.error instanceof ApiError && m.error.code === "gift_own";
  return (
    <div className="mx-auto flex min-h-[80dvh] max-w-xl flex-col items-center justify-center px-8 text-center">
      <div className="relative">
        <AnimatePresence>{r && <Confetti key="c" count={34} spread={180} />}</AnimatePresence>
        <motion.div initial={{ opacity: 0, y: 24, rotate: -3 }} animate={r ? { opacity: 1, y: 0, rotate: 0, scale: [1, 1.06, 1] } : { opacity: 1, y: 0, rotate: -1.5 }}
          transition={r ? { duration: 0.5, ease: ease.outExpo } : spring.soft}>
          <Arch className="h-[220px] w-[168px]" outlineClass="text-ink">
            <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-vellum pt-8 text-ink">
              {r ? (
                <>
                  <span className="font-serif text-[64px] leading-none font-light">+<CountUp value={r.searches} /></span>
                  <span className="caption text-ink-2">{plural(r.searches, "поиск", "поиска", "поисков")}</span>
                </>
              ) : (
                <motion.span animate={m.isPending ? { rotate: [0, -8, 8, -5, 0] } : { y: [0, -4, 0] }}
                  transition={m.isPending ? { duration: 0.5, repeat: Infinity } : { duration: 2.4, repeat: Infinity, ease: ease.inOut }}>
                  <IconGift size={44} strokeWidth={1.25} />
                </motion.span>
              )}
            </div>
          </Arch>
        </motion.div>
      </div>
      <Ornament className="mt-8 w-40 text-relic" draw />
      {r ? (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <h1 className="mt-6 font-serif text-[36px] leading-[38px] font-light">Подарок <i className="font-normal">принят</i></h1>
          <p className="mt-2 text-[15px] text-ink-2">{r.from_name} дарит вам {r.searches} {plural(r.searches, "поиск", "поиска", "поисков")} по фото. Они уже на счету.</p>
          <Link to="/"><Button className="mt-6 w-full min-w-64">Найти вещь по фото</Button></Link>
        </motion.div>
      ) : (
        <>
          <h1 className="mt-6 font-serif text-[36px] leading-[38px] font-light">Вам <i className="font-normal">подарок</i></h1>
          <p className="mt-2 max-w-xs text-[15px] text-ink-2">Бонусные поиски по фото: SIFT найдёт вещь на всех маркетплейсах и сравнит цены.</p>
          {m.error && <p className="mt-4 text-sm text-bad">{(m.error as Error).message}</p>}
          {own ? (
            <Link to="/gifts"><Button variant="secondary" className="mt-6 min-w-64">К моим подаркам</Button></Link>
          ) : m.error ? (
            <Link to="/"><Button variant="secondary" className="mt-6 min-w-64">На главную</Button></Link>
          ) : (
            <Button className="mt-6 min-w-64" loading={m.isPending} onClick={() => m.mutate()}>Принять подарок</Button>
          )}
        </>
      )}
      <div className="mt-10 text-ink-3"><Sieve cols={9} width={40} accent={null} /></div>
    </div>
  );
}
