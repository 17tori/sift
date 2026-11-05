import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Ornament, Stamp } from "../components/archive";
import { Confetti } from "../components/Confetti";
import { IconCopy, IconGift } from "../components/icons";
import { Badge, Button, cx, Empty, ErrorView, PageHeader, SectionTitle, Skeleton } from "../components/ui";
import { api, waitPaid } from "../lib/api";
import { date, plural } from "../lib/format";
import { cardVariants, rowVariants } from "../lib/motion";
import { copyText, haptic, openInvoice, shareMessage } from "../lib/telegram";
import { toast } from "../lib/toast";
import type { Gift, GiftPack, Invoice } from "../lib/types";

const STATUS: Record<string, { label: string; tone: "accent" | "good" | "neutral" | "bad" }> = {
  active: { label: "Ждёт друга", tone: "accent" },
  redeemed: { label: "Принят", tone: "good" },
  refunded: { label: "Возврат", tone: "bad" },
};

const giftText = (n: number) => `Дарю ${n} ${plural(n, "поиск", "поиска", "поисков")} по фото в SIFT: находит вещь на всех маркетплейсах`;

export function sendGift(g: Gift) {
  return shareMessage(null, g.link, giftText(g.searches));
}

export default function Gifts() {
  const qc = useQueryClient();
  const packs = useQuery({ queryKey: ["gift-packs"], queryFn: () => api.get<GiftPack[]>("/api/v1/gifts/packs"), staleTime: 300_000 });
  const mine = useQuery({ queryKey: ["gifts"], queryFn: () => api.get<Gift[]>("/api/v1/gifts") });
  const [buying, setBuying] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Gift | null>(null);

  const buy = async (p: GiftPack) => {
    setBuying(p.code);
    try {
      const inv = await api.post<Invoice>("/api/v1/gifts/invoice", { pack: p.code });
      const status = await openInvoice(inv.invoice_link);
      if (status === "paid") {
        await waitPaid(inv.intent_id);
        const list = await qc.fetchQuery({ queryKey: ["gifts"], queryFn: () => api.get<Gift[]>("/api/v1/gifts") });
        haptic.success();
        setFresh(list.find((g) => g.status === "active") ?? null);
      } else if (status === "failed") {
        haptic.error();
        toast("Оплата не прошла", "bad");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Не удалось создать счёт", "bad");
    } finally {
      setBuying(null);
    }
  };

  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader numeral="XI" label="Дары" title="Подарить *поиски*" subtitle="Друг получит ссылку и бонусные поиски по фото. Оплата в Telegram Stars." />
      <div className="space-y-3 px-5">
        <AnimatePresence>
          {fresh && (
            <motion.div key={fresh.code} className="relative overflow-visible" initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
              <Confetti />
              <div className="flex flex-col items-center gap-3 bg-vellum px-5 py-6 text-center shadow-[inset_0_0_0_1px_var(--line)]">
                <Ornament className="w-full text-relic" draw />
                <p className="font-serif text-[30px] leading-8 font-light">Подарок <i className="font-normal">готов</i></p>
                <p className="text-[14px] text-ink-2">{fresh.searches} {plural(fresh.searches, "поиск", "поиска", "поисков")}. Ссылка одноразовая: её активирует первый, кто откроет.</p>
                <Button className="mt-1 w-full" onClick={() => sendGift(fresh)}>Отправить другу</Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {packs.isError ? <ErrorView error={packs.error} retry={() => packs.refetch()} /> : packs.isLoading ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)
        ) : !packs.data?.length ? (
          <Empty icon={<IconGift size={26} />} title="Подарки *скоро*" text="Подарочные поиски сейчас недоступны." />
        ) : (
          packs.data.map((p, i) => {
            const popular = i === 1;
            const per = p.stars / p.searches;
            return (
              <motion.article key={p.code} custom={i} variants={cardVariants} initial="hidden" animate="show"
                className={cx("relative flex items-center gap-4 p-[18px]", popular ? "shadow-[inset_0_0_0_1.5px_var(--accent)]" : "shadow-[inset_0_0_0_1px_var(--line-strong)]")}>
                <span aria-hidden className="pointer-events-none absolute inset-[5px] shadow-[inset_0_0_0_1px_var(--line)]" />
                <div className="w-[76px] text-center">
                  <p className="font-serif text-[46px] leading-[44px]">{p.searches}</p>
                  <p className="caption text-ink-3">{plural(p.searches, "поиск", "поиска", "поисков")}</p>
                </div>
                <div className="flex-1">
                  <p className="font-mono text-[17px] font-semibold tnum">{p.stars} ⭐</p>
                  <p className="caption mt-1 text-ink-3">≈ {per.toFixed(1).replace(".", ",")} ⭐ за поиск</p>
                  {popular && <div className="mt-2"><Badge tone="accent">Выгодно</Badge></div>}
                </div>
                <Button className="h-11 px-4" variant={popular ? "primary" : "secondary"} loading={buying === p.code} onClick={() => buy(p)}>Подарить</Button>
              </motion.article>
            );
          })
        )}

        <p className="px-1 pt-1 text-xs leading-relaxed text-ink-3">
          Подарок нельзя активировать самому. Если друг впервые в боте, он придёт по вашему приглашению. Неиспользованный подарок можно вернуть через поддержку.
        </p>

        <section className="pt-5">
          <SectionTitle>Мои подарки</SectionTitle>
          {mine.data?.length ? (
            <ul className="border-t border-line">
              {mine.data.map((g, i) => {
                const st = STATUS[g.status] ?? { label: g.status, tone: "neutral" as const };
                return (
                  <motion.li key={g.code} custom={i} variants={rowVariants} initial="hidden" animate="show" className="flex items-center gap-3 border-b border-line py-3">
                    <Stamp muted={g.status !== "active"}>{g.searches} шт</Stamp>
                    <div className="min-w-0 flex-1">
                      <p className="text-[14px]">{date(g.created_at, true)}</p>
                      <div className="mt-1"><Badge tone={st.tone}>{st.label}</Badge></div>
                    </div>
                    {g.status === "active" && (
                      <>
                        <button className="grid h-9 w-9 place-items-center rounded-full text-ink-2 shadow-[inset_0_0_0_1px_var(--line)]" aria-label="Скопировать ссылку"
                          onClick={async () => { if (await copyText(g.link)) toast("Ссылка скопирована", "good"); }}>
                          <IconCopy size={16} />
                        </button>
                        <Button className="h-9 px-3 text-[13px]" variant="secondary" onClick={() => sendGift(g)}>Отправить</Button>
                      </>
                    )}
                  </motion.li>
                );
              })}
            </ul>
          ) : <p className="rounded-2xl bg-surface-2 px-4 py-4 text-center text-sm text-ink-2">{mine.isLoading ? "Загружаем…" : "Вы ещё не дарили поиски"}</p>}
        </section>
      </div>
    </div>
  );
}
