import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useState } from "react";
import { IconCheck, IconGift } from "../components/icons";
import { Badge, Button, Card, cx, ErrorView, PageHeader, SectionTitle, Skeleton, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { date, MODE_LABEL, timeLeft } from "../lib/format";
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
  if (p.priority > 0) out.push(p.priority >= 9 ? "Максимальный приоритет" : "Приоритетная обработка");
  if (f.early_access) out.push("Ранний доступ к новым функциям");
  return out;
}

async function waitPaid(intentId: string): Promise<boolean> {
  for (let i = 0; i < 20; i++) {
    const r = await api.get<{ status: string }>(`/api/v1/payments/intents/${intentId}`);
    if (r.status === "paid") return true;
    await new Promise((res) => setTimeout(res, 1500));
  }
  return false;
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
      <Card className="flex items-center gap-4 p-4">
        <span className="grid h-11 w-11 place-items-center rounded-2xl bg-accent text-white"><IconGift size={22} /></span>
        <div><p className="font-semibold">Пробный PRO активен</p><p className="text-xs text-ink-2">Осталось {timeLeft(me.trial.ends_at)} · без автосписания</p></div>
      </Card>
    );
  }
  if (!me.trial.available) return null;
  return (
    <Card className="overflow-hidden p-5">
      <p className="font-mono text-[11px] tracking-[0.14em] text-accent uppercase">Trial</p>
      <p className="mt-1 font-display text-xl font-semibold">{me.trial.days} дня PRO бесплатно</p>
      <p className="mt-1 text-sm text-ink-2">Один раз на аккаунт. После окончания вы вернётесь на Free, деньги не спишутся.</p>
      {m.error && <p className="mt-2 text-sm text-bad">{(m.error as Error).message}</p>}
      <Button className="mt-4 w-full" loading={m.isPending} onClick={() => m.mutate()}>Активировать пробный период</Button>
    </Card>
  );
}

export default function Subscription() {
  const { data: me, error, refetch } = useMe();
  const plans = usePlans();
  const qc = useQueryClient();
  const [buying, setBuying] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
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
        setMsg(ok ? { ok: true, text: `${p.title} активирован. Спасибо!` } : { ok: true, text: "Оплата принята, подтверждение придёт в чат с ботом." });
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
      <PageHeader title="Подписка" subtitle="Оплата в Telegram Stars" />
      <div className="space-y-4 px-4">
        {me && <TrialCard me={me} />}
        {msg && <p className={cx("rounded-2xl px-4 py-3 text-sm", msg.ok ? "bg-good/12 text-good" : "bg-bad/12 text-bad")}>{msg.text}</p>}

        {plans.isLoading || !me ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-56 rounded-[20px]" />)
        ) : (
          plans.data?.map((p, i) => {
            const current = me.plan.code === p.code;
            const popular = p.code === "pro";
            return (
              <motion.div key={p.code} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                <Card className={cx("p-5", popular && "ring-2 ring-accent")}>
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-display text-xl font-bold tracking-tight">{p.title}</p>
                        {popular && <Badge tone="accent">Популярный</Badge>}
                        {current && <Badge tone="good">Текущий</Badge>}
                      </div>
                      <p className="mt-1 text-sm text-ink-2">{p.description}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-2xl font-semibold">{p.price_stars}<span className="ml-1 text-base">⭐</span></p>
                      <p className="text-xs text-ink-3">{p.price_stars ? `за ${p.period_days} дн.` : "навсегда"}</p>
                    </div>
                  </div>
                  <ul className="mt-4 space-y-2">
                    {features(p).map((f) => (
                      <li key={f} className="flex items-start gap-2 text-[14px]"><IconCheck size={17} className="mt-0.5 shrink-0 text-accent" />{f}</li>
                    ))}
                  </ul>
                  {p.price_stars > 0 && (
                    <Button className="mt-5 w-full" variant={popular ? "primary" : "secondary"} loading={buying === p.code} onClick={() => buy(p)}>
                      {current && !me.trial.active ? "Продлить" : `Оформить за ${p.price_stars} ⭐`}
                    </Button>
                  )}
                </Card>
              </motion.div>
            );
          })
        )}

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
            <ul className="divide-y divide-line overflow-hidden rounded-[20px] bg-surface ring-1 ring-line">
              {payments.data.map((p) => (
                <li key={p.id} className="flex items-center justify-between px-4 py-3">
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
