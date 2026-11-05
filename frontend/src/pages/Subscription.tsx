import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Ornament, Stamp } from "../components/archive";
import { useState } from "react";
import { IconStar } from "../components/icons";
import { Badge, Button, Card, cx, ErrorView, PageHeader, SectionTitle, Skeleton, Toggle } from "../components/ui";
import { api, waitPaid } from "../lib/api";
import { date, MODE_LABEL, plural, timeLeft } from "../lib/format";
import { cardVariants, ease } from "../lib/motion";
import { useMe, usePlans } from "../lib/queries";
import { confirm, haptic, openInvoice } from "../lib/telegram";
import type { Me, Payment, Plan, Subscription as Sub } from "../lib/types";

function features(p: Plan): string[] {
  const f = p.features;
  const out = [`${p.search_limit} поисков ${p.limit_window === "day" ? "в день" : "в месяц"}`];
  out.push(f.marketplaces === "all" ? "Все доступные маркетплейсы" : "Основные маркетплейсы");
  out.push(`Режимы: ${(f.modes ?? []).map((m) => MODE_LABEL[m]?.title).join(", ")}`);
  if (f.advanced_filters) out.push("Расширенные фильтры");
  out.push((f.history_days ?? 0) >= 3650 ? "Полная история поисков" : `История ${f.history_days} дней`);
  if (f.deep_analysis) out.push("Глубокий AI-анализ фото");
  if (f.price_alerts) out.push("Уведомления о снижении цены");
  if ((f.watch_limit ?? 0) > 0) out.push(`Отслеживание ${f.watch_limit} ${plural(f.watch_limit ?? 0, "вещи", "вещей", "вещей")}: дешевле или на новой площадке`);
  if (p.priority > 0) out.push(p.priority >= 9 ? "Максимальный приоритет" : "Приоритетная обработка");
  if (f.early_access) out.push("Ранний доступ к новым функциям");
  return out;
}

const ROMAN = ["I", "II", "III", "IV", "V"];

/** XI. Payment seal: check stroke draws in, ten stars rise. */
function PaidSeal() {
  const reduce = useReducedMotion();
  return (
    <motion.div className="relative flex flex-col items-center gap-3 py-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <svg width="64" height="64" viewBox="0 0 64 64" aria-hidden>
        <circle cx="32" cy="32" r="30" fill="none" stroke="var(--line-strong)" />
        <motion.path d="M20 33 L29 42 L45 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          initial={{ pathLength: reduce ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.7, delay: 0.3, ease: ease.ritual }} />
      </svg>
      <p className="font-serif text-[28px] font-light">Принят <i className="font-normal">в архив</i></p>
      {!reduce && Array.from({ length: 10 }).map((_, i) => (
        <motion.span key={i} className="absolute top-6 text-accent" style={{ left: `${8 + i * 9}%` }}
          initial={{ opacity: 0, y: 0, scale: 0.4 }} animate={{ opacity: [0, 1, 0], y: -40 - (i % 3) * 40, rotate: 160, scale: 1 }}
          transition={{ duration: 0.9, delay: (i % 4) * 0.06, ease: ease.outExpo }}>
          <IconStar size={9} fill="currentColor" />
        </motion.span>
      ))}
    </motion.div>
  );
}

function TrialCard({ me }: { me: Me }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api.post<Me>("/api/v1/trial/activate"),
    onSuccess: (data) => { haptic.success(); qc.setQueryData(["me"], data); },
    onError: () => haptic.error(),
  });
  if (me.trial.active && me.trial.ends_at) {
    return (
      <Card vellum className="flex items-center gap-4 p-4">
        <Stamp>PRO</Stamp>
        <div><p className="font-semibold">Пробный PRO активен</p><p className="caption mt-0.5 text-ink-3">Осталось {timeLeft(me.trial.ends_at)} · без автосписания</p></div>
      </Card>
    );
  }
  if (!me.trial.available) return null;
  return (
    <Card vellum className="flex flex-col gap-3 p-[18px]">
      <Ornament className="text-relic" />
      <p className="flex items-baseline gap-2.5"><span className="font-serif text-[44px] leading-10 italic">{me.trial.days} {plural(me.trial.days, "день", "дня", "дней")}</span>
        <span className="font-display text-[17px] font-bold">PRO бесплатно</span></p>
      <p className="text-[13px] leading-[18px] text-ink-2">Без автосписания: по окончании вы вернётесь на Free. Один раз на аккаунт.</p>
      {m.error && <p className="text-sm text-bad">{(m.error as Error).message}</p>}
      <Button variant="secondary" className="h-[46px] w-full" loading={m.isPending} onClick={() => m.mutate()}>Активировать пробный период</Button>
    </Card>
  );
}

export default function Subscription() {
  const { data: me, error, refetch } = useMe();
  const plans = usePlans();
  const qc = useQueryClient();
  const [buying, setBuying] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [sealed, setSealed] = useState<string | null>(null);
  const reduce = useReducedMotion();
  const payments = useQuery({ queryKey: ["payments"], queryFn: () => api.get<Payment[]>("/api/v1/payments") });
  const renew = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => api.post<Sub>(`/api/v1/subscriptions/${id}/auto-renew`, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });

  const buy = async (p: Plan) => {
    setMsg(null);
    setBuying(p.code);
    try {
      const inv = await api.post<{ intent_id: string; invoice_link: string; recurring: boolean }>("/api/v1/payments/invoice", { plan_code: p.code });
      const status = await openInvoice(inv.invoice_link);
      if (status === "paid") {
        // Telegram reports "paid" client-side; the subscription is granted only after the bot receives successful_payment.
        const ok = await waitPaid(inv.intent_id);
        await qc.invalidateQueries({ queryKey: ["me"] });
        await qc.invalidateQueries({ queryKey: ["payments"] });
        haptic.success();
        if (ok) setSealed(p.code);
        setMsg(ok ? { ok: true, text: `${p.title} принят в архив.` } : { ok: true, text: "Оплата принята, подтверждение придёт в чат с ботом." });
      } else if (status === "failed") {
        haptic.error();
        setMsg({ ok: false, text: "Оплата не прошла. Попробуйте ещё раз." });
      }
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Не удалось создать счёт." });
    } finally {
      setBuying(null);
    }
  };

  if (error) return <ErrorView error={error} retry={() => refetch()} />;
  const sub = me?.subscription;
  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader numeral="IX" label="Подписка" title="Расширь *архив*." subtitle="Оплата в Telegram Stars" />
      <div className="space-y-3 px-5">
        {me && <TrialCard me={me} />}
        {msg && <p className={cx("caption py-2", msg.ok ? "text-good" : "text-bad")}>{msg.text}</p>}

        {plans.isLoading || !me ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-56 rounded-[20px]" />)
        ) : (
          plans.data?.map((p, i) => {
            const current = me.plan.code === p.code;
            const popular = p.code === "pro";
            const roman = ROMAN[i] ?? String(i + 1);
            return (
              <motion.article key={p.code} custom={i} variants={cardVariants} initial="hidden" animate="show"
                className={cx("relative overflow-hidden p-[1.5px]", !popular && "shadow-[inset_0_0_0_1px_var(--line-strong)]")}>
                {popular && !reduce && (
                  <motion.span aria-hidden className="absolute -top-[200%] -left-1/2 h-[500%] w-[200%]"
                    style={{ background: "conic-gradient(from 0deg, var(--accent), #9DABFF, var(--accent), #2E44C9, var(--accent))" }}
                    animate={{ rotate: 360 }} transition={{ duration: 4, repeat: Infinity, ease: "linear" }} />
                )}
                {popular && reduce && <span aria-hidden className="absolute inset-0 bg-accent" />}
                <div className="relative flex flex-col gap-3 bg-bg px-[18px] pt-5 pb-[18px]">
                  <span aria-hidden className="pointer-events-none absolute inset-[5px] shadow-[inset_0_0_0_1px_var(--line)]" />
                  <div className="flex items-start gap-3.5">
                    <span className="w-[52px] font-serif text-[48px] leading-10">{roman}</span>
                    <div className="flex-1 pt-0.5">
                      <p className="font-display text-[19px] font-bold tracking-[-0.02em]">{p.title}</p>
                      <p className="mt-1 font-mono text-[13px] text-ink-2 tnum">{p.price_stars} ⭐{p.price_stars ? ` / ${p.period_days} дней` : ""}</p>
                    </div>
                    {sealed === p.code ? <Stamp land className="h-[26px] -rotate-2 text-[13px]">{p.title}</Stamp>
                      : popular ? <Badge tone="accent">Популярный</Badge> : current ? <Badge>Текущий</Badge> : null}
                  </div>
                  <div className="ml-[66px] h-px bg-line" />
                  <ul className="ml-[66px] flex flex-col gap-[7px]">
                    {features(p).map((f) => <li key={f} className="flex gap-2 text-[13px] leading-[18px] text-ink-2"><span className="text-ink-3">—</span>{f}</li>)}
                  </ul>
                  {p.price_stars > 0 && (
                    <Button className="mt-2 w-full" variant={popular ? "primary" : "secondary"} loading={buying === p.code} onClick={() => buy(p)}>
                      {current && !me.trial.active ? "Продлить" : `Оформить за ${p.price_stars} ⭐`}
                    </Button>
                  )}
                </div>
              </motion.article>
            );
          })
        )}
        <AnimatePresence>{sealed && <PaidSeal key={sealed} />}</AnimatePresence>

        {sub && sub.is_recurring && !me?.trial.active && (
          <Card className="flex items-center gap-4 p-4">
            <div className="flex-1">
              <p className="text-[15px] font-medium">Автопродление</p>
              <p className="text-xs text-ink-2">{sub.auto_renew ? `Следующее списание ${date(sub.expires_at)}` : `Доступ сохранится до ${date(sub.expires_at)}`}</p>
            </div>
            <Toggle checked={sub.auto_renew} disabled={renew.isPending} onChange={async (v) => {
              if (!v && !(await confirm("Отключить автопродление? Доступ сохранится до конца оплаченного периода."))) return;
              renew.mutate({ id: sub.id, enabled: v });
            }} />
          </Card>
        )}

        <p className="px-1 text-xs leading-relaxed text-ink-3">
          Подписка активируется только после подтверждения оплаты Telegram. Стоимость и лимиты могут меняться, уже оплаченный период сохраняется.
          Вопросы по оплате и возвраты — через раздел «Поддержка».
        </p>

        <section id="payments" className="pt-4">
          <SectionTitle>История платежей</SectionTitle>
          {payments.data?.length ? (
            <ul className="divide-y divide-line border-y border-line">
              {payments.data.map((p) => (
                <li key={p.id} className="flex items-center justify-between py-3">
                  <div><p className="text-[14px] font-medium uppercase">{p.plan_code}{p.is_recurring ? " · автопродление" : ""}</p><p className="text-xs text-ink-3">{date(p.created_at, true)}</p></div>
                  <div className="text-right"><p className="font-mono">{p.amount_stars} ⭐</p>{p.status === "refunded" && <p className="text-xs text-bad">возврат</p>}</div>
                </li>
              ))}
            </ul>
          ) : <p className="rounded-2xl bg-surface-2 px-4 py-4 text-center text-sm text-ink-2">Платежей пока нет</p>}
        </section>
      </div>
    </div>
  );
}
