import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { TimeChart } from "../../components/Chart";
import { Badge, Button, Card, cx, ErrorView, Field, inputClass, PageHeader, Segmented, Skeleton, Toggle } from "../../components/ui";
import { api, qs } from "../../lib/api";
import { date, num } from "../../lib/format";
import { useMe } from "../../lib/queries";
import { confirm, haptic } from "../../lib/telegram";
import type { Me, Payment, Plan, Subscription } from "../../lib/types";

const TABS = [
  ["", "Обзор"], ["users", "Пользователи"], ["plans", "Тарифы"], ["settings", "Trial и рефералы"],
  ["payments", "Платежи"], ["integrations", "Интеграции"], ["errors", "Ошибки"],
] as const;

function Tabs() {
  return (
    <div className="no-scrollbar -mx-4 mb-4 flex gap-2 overflow-x-auto px-4">
      {TABS.map(([to, label]) => (
        <NavLink key={to} to={`/admin/${to}`} end={to === ""}
          className={({ isActive }) => cx("h-9 shrink-0 rounded-full px-3.5 text-[13px] leading-9 font-medium", isActive ? "bg-ink text-bg" : "bg-surface-2 text-ink-2")}>
          {label}
        </NavLink>
      ))}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <Card className="p-4">
      <p className="text-[12px] text-ink-3">{label}</p>
      <p className="mt-1 font-mono text-[22px] font-semibold">{typeof value === "number" ? num(value) : value}</p>
      {hint && <p className="text-[11px] text-ink-3">{hint}</p>}
    </Card>
  );
}

function Dashboard() {
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const ov = useQuery({ queryKey: ["admin", "overview"], queryFn: () => api.get<Record<string, number>>("/api/v1/admin/overview"), refetchInterval: 30000 });
  const ts = useQuery({ queryKey: ["admin", "stats", days], queryFn: () => api.get<{ date: string; users: number; searches: number; revenue: number; active: number }[]>(`/api/v1/admin/stats?days=${days}`) });
  if (ov.isError) return <ErrorView error={ov.error} retry={() => ov.refetch()} />;
  const o = ov.data;
  const s = ts.data ?? [];
  return (
    <div className="space-y-4">
      {!o ? <Skeleton className="h-64 rounded-[20px]" /> : (
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Пользователи" value={o.users_total} hint={`${num(o.users_active_24h)} активны за 24 ч`} />
          <Stat label="Активны 7 дней" value={o.users_active_7d} hint={`${num(o.users_blocked)} заблокировано`} />
          <Stat label="PRO" value={o.pro_active} />
          <Stat label="ULTRA" value={o.ultra_active} />
          <Stat label="Активные trial" value={o.trials_active} />
          <Stat label="Поиски за сутки" value={o.searches_24h} hint={`${num(o.searches_failed_24h)} с ошибкой`} />
          <Stat label="Выручка, ⭐" value={o.revenue_stars_total} hint={`${num(o.revenue_stars_30d)} за 30 дней`} />
          <Stat label="Возвраты" value={o.refunds_total} />
        </div>
      )}
      <Segmented value={days} onChange={setDays} options={[{ value: "7", label: "7 дней" }, { value: "30", label: "30 дней" }, { value: "90", label: "90 дней" }]} />
      {ts.isLoading ? <Skeleton className="h-52 rounded-[20px]" /> : (
        <>
          <TimeChart title="Новые пользователи" data={s.map((d) => ({ date: d.date, value: d.users }))} />
          <TimeChart title="Активные пользователи (искали)" data={s.map((d) => ({ date: d.date, value: d.active }))} />
          <TimeChart title="Поиски" data={s.map((d) => ({ date: d.date, value: d.searches }))} />
          <TimeChart title="Выручка" unit="⭐" kind="bar" data={s.map((d) => ({ date: d.date, value: d.revenue }))} />
        </>
      )}
    </div>
  );
}

interface UserRow { id: number; telegram_id: number; username: string | null; first_name: string; created_at: string; last_seen_at: string; is_blocked: boolean; bonus_searches: number; plan: string; searches: number }

function Users() {
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const users = useQuery({ queryKey: ["admin", "users", q], queryFn: () => api.get<UserRow[]>(`/api/v1/admin/users${qs({ q })}`) });
  return (
    <div className="space-y-3">
      <input className={inputClass} placeholder="Поиск: @username, имя или Telegram ID" value={q} onChange={(e) => setQ(e.target.value)} />
      {users.isLoading ? <Skeleton className="h-64 rounded-[20px]" /> : (
        <ul className="divide-y divide-line overflow-hidden rounded-[20px] bg-surface ring-1 ring-line">
          {users.data?.map((u) => (
            <li key={u.id} onClick={() => nav(`/admin/users/${u.id}`)} className="flex cursor-pointer items-center gap-3 px-4 py-3 active:bg-surface-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium">{u.first_name} {u.username && <span className="text-ink-3">@{u.username}</span>}</p>
                <p className="font-mono text-[11px] text-ink-3">{u.telegram_id} · {u.searches} поисков · {date(u.last_seen_at, true)}</p>
              </div>
              {u.is_blocked ? <Badge tone="bad">blocked</Badge> : <Badge tone={u.plan === "free" ? "neutral" : "accent"}>{u.plan}</Badge>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UserDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const d = useQuery({ queryKey: ["admin", "user", id], queryFn: () => api.get<{ user: Me; is_blocked: boolean; blocked_reason: string | null; subscriptions: Subscription[]; payments: Payment[] }>(`/api/v1/admin/users/${id}`) });
  const [plan, setPlan] = useState("pro");
  const [days, setDays] = useState("30");
  const [bonus, setBonus] = useState("5");
  const refresh = () => { haptic.success(); qc.invalidateQueries({ queryKey: ["admin"] }); };
  const block = useMutation({ mutationFn: (blocked: boolean) => api.post(`/api/v1/admin/users/${id}/block`, { blocked, reason: blocked ? "admin" : null }), onSuccess: refresh });
  const grant = useMutation({ mutationFn: () => api.post(`/api/v1/admin/users/${id}/subscription`, { plan_code: plan, days: Number(days) }), onSuccess: refresh });
  const addBonus = useMutation({ mutationFn: () => api.post(`/api/v1/admin/users/${id}/bonus`, { delta: Number(bonus) }), onSuccess: refresh });
  const revoke = useMutation({ mutationFn: (sid: number) => api.post(`/api/v1/admin/subscriptions/${sid}/revoke`), onSuccess: refresh });
  if (d.isError) return <ErrorView error={d.error} />;
  if (!d.data) return <Skeleton className="h-64 rounded-[20px]" />;
  const { user: u } = d.data;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <p className="font-display text-lg font-semibold">{u.first_name} {u.username && <span className="text-ink-3">@{u.username}</span>}</p>
        <p className="font-mono text-xs text-ink-3">TG {u.telegram_id} · с {date(u.created_at)}</p>
        <p className="mt-2 text-sm">Тариф: <b>{u.plan.title}</b>{u.subscription && ` до ${date(u.subscription.expires_at)}`} · поиски {u.quota.used}/{u.quota.limit} · бонус {u.quota.bonus}</p>
        <p className="text-sm text-ink-2">Trial: {u.trial.used ? (u.trial.active ? "активен" : "использован") : "не использован"} · всего поисков {u.total_searches}</p>
        <Button variant={d.data.is_blocked ? "secondary" : "danger"} className="mt-4 h-10 w-full" loading={block.isPending}
          onClick={async () => { if (await confirm(d.data.is_blocked ? "Разблокировать пользователя?" : "Заблокировать пользователя?")) block.mutate(!d.data.is_blocked); }}>
          {d.data.is_blocked ? "Разблокировать" : "Заблокировать"}
        </Button>
      </Card>
      <Card className="space-y-3 p-4">
        <p className="font-semibold">Выдать подписку вручную</p>
        <div className="grid grid-cols-2 gap-3">
          <select className={inputClass} value={plan} onChange={(e) => setPlan(e.target.value)}><option value="pro">PRO</option><option value="ultra">ULTRA</option></select>
          <input className={inputClass} inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))} placeholder="дней" />
        </div>
        <Button className="h-10 w-full" loading={grant.isPending} onClick={() => grant.mutate()}>Выдать</Button>
        {grant.error && <p className="text-sm text-bad">{(grant.error as Error).message}</p>}
        <p className="pt-2 font-semibold">Бонусные поиски</p>
        <div className="flex gap-3">
          <input className={inputClass} inputMode="numeric" value={bonus} onChange={(e) => setBonus(e.target.value.replace(/[^\d-]/g, ""))} />
          <Button className="h-12 shrink-0" variant="secondary" loading={addBonus.isPending} onClick={() => addBonus.mutate()}>Начислить</Button>
        </div>
      </Card>
      <Card className="p-4">
        <p className="mb-2 font-semibold">Подписки</p>
        {d.data.subscriptions.length === 0 && <p className="text-sm text-ink-3">Нет</p>}
        {d.data.subscriptions.map((s) => (
          <div key={s.id} className="flex items-center justify-between border-b border-line py-2 text-sm last:border-0">
            <span className="uppercase">{s.plan_code} · {s.source} · {s.status}<br /><span className="font-mono text-[11px] text-ink-3 normal-case">до {date(s.expires_at, true)}</span></span>
            {s.status === "active" && <button className="text-bad" onClick={async () => { if (await confirm("Отозвать подписку?")) revoke.mutate(s.id); }}>Отозвать</button>}
          </div>
        ))}
      </Card>
    </div>
  );
}

function Plans() {
  const qc = useQueryClient();
  const plans = useQuery({ queryKey: ["admin", "plans"], queryFn: () => api.get<Plan[]>("/api/v1/admin/plans") });
  const save = useMutation({
    mutationFn: ({ code, body }: { code: string; body: Partial<Plan> }) => api.patch<Plan>(`/api/v1/admin/plans/${code}`, body as Record<string, unknown>),
    onSuccess: () => { haptic.success(); qc.invalidateQueries({ queryKey: ["admin", "plans"] }); qc.invalidateQueries({ queryKey: ["plans"] }); },
  });
  if (!plans.data) return <Skeleton className="h-64 rounded-[20px]" />;
  return <div className="space-y-4">{plans.data.map((p) => <PlanEditor key={p.code} plan={p} onSave={(body) => save.mutate({ code: p.code, body })} saving={save.isPending} />)}</div>;
}

function PlanEditor({ plan, onSave, saving }: { plan: Plan; onSave: (b: Partial<Plan>) => void; saving: boolean }) {
  const [p, setP] = useState(plan);
  const f = p.features;
  const setF = (k: keyof Plan["features"], v: unknown) => setP({ ...p, features: { ...p.features, [k]: v } });
  const modes = ["exact", "similar", "cheaper", "discover"] as const;
  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center justify-between"><p className="font-display text-lg font-semibold">{plan.code.toUpperCase()}</p><Toggle checked={p.is_active} onChange={(v) => setP({ ...p, is_active: v })} /></div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Название"><input className={inputClass} value={p.title} onChange={(e) => setP({ ...p, title: e.target.value })} /></Field>
        <Field label="Цена, ⭐"><input className={inputClass} inputMode="numeric" disabled={plan.code === "free"} value={p.price_stars} onChange={(e) => setP({ ...p, price_stars: Number(e.target.value.replace(/\D/g, "")) })} /></Field>
        <Field label="Лимит поисков"><input className={inputClass} inputMode="numeric" value={p.search_limit} onChange={(e) => setP({ ...p, search_limit: Number(e.target.value.replace(/\D/g, "")) })} /></Field>
        <Field label="Период лимита">
          <select className={inputClass} value={p.limit_window} onChange={(e) => setP({ ...p, limit_window: e.target.value as "day" | "month" })}><option value="day">день</option><option value="month">месяц</option></select>
        </Field>
        <Field label="История, дней"><input className={inputClass} inputMode="numeric" value={f.history_days ?? 0} onChange={(e) => setF("history_days", Number(e.target.value.replace(/\D/g, "")))} /></Field>
        <Field label="Кандидатов на поиск"><input className={inputClass} inputMode="numeric" value={f.max_candidates ?? 40} onChange={(e) => setF("max_candidates", Number(e.target.value.replace(/\D/g, "")))} /></Field>
      </div>
      <Field label="Описание"><input className={inputClass} value={p.description} onChange={(e) => setP({ ...p, description: e.target.value })} /></Field>
      <Field label="Режимы">
        <div className="flex flex-wrap gap-2">{modes.map((m) => (
          <button key={m} onClick={() => setF("modes", (f.modes ?? []).includes(m) ? (f.modes ?? []).filter((x) => x !== m) : [...(f.modes ?? []), m])}
            className={cx("h-8 rounded-full px-3 text-[12px]", (f.modes ?? []).includes(m) ? "bg-ink text-bg" : "bg-surface-2 text-ink-2")}>{m}</button>))}
        </div>
      </Field>
      {([["advanced_filters", "Расширенные фильтры"], ["deep_analysis", "Глубокий AI-анализ"], ["price_alerts", "Уведомления о цене"], ["early_access", "Ранний доступ"]] as const).map(([k, l]) => (
        <div key={k} className="flex items-center justify-between text-sm"><span>{l}</span><Toggle checked={!!f[k]} onChange={(v) => setF(k, v)} /></div>
      ))}
      <div className="flex items-center justify-between text-sm"><span>Все маркетплейсы</span><Toggle checked={f.marketplaces === "all"} onChange={(v) => setF("marketplaces", v ? "all" : "basic")} /></div>
      <Button className="h-10 w-full" loading={saving} onClick={() => onSave({ title: p.title, description: p.description, price_stars: p.price_stars, search_limit: p.search_limit, limit_window: p.limit_window, is_active: p.is_active, features: p.features })}>Сохранить</Button>
    </Card>
  );
}

function AppSettings() {
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["admin", "settings"], queryFn: () => api.get<{ trial: Record<string, unknown>; referral: Record<string, number | boolean>; basic_marketplaces: string[] }>("/api/v1/admin/settings") });
  const put = useMutation({ mutationFn: ({ key, value }: { key: string; value: unknown }) => api.put(`/api/v1/admin/settings/${key}`, value as Record<string, unknown>),
    onSuccess: () => { haptic.success(); qc.invalidateQueries({ queryKey: ["admin", "settings"] }); } });
  const [trial, setTrial] = useState<Record<string, unknown> | null>(null);
  const [ref, setRef] = useState<Record<string, number | boolean> | null>(null);
  if (!s.data) return <Skeleton className="h-64 rounded-[20px]" />;
  const t = trial ?? s.data.trial, r = ref ?? s.data.referral;
  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        <p className="font-semibold">Пробный период</p>
        <div className="flex items-center justify-between text-sm"><span>Включён</span><Toggle checked={!!t.enabled} onChange={(v) => setTrial({ ...t, enabled: v })} /></div>
        <div className="flex items-center justify-between text-sm"><span>Активировать при первом /start</span><Toggle checked={!!t.auto_activate} onChange={(v) => setTrial({ ...t, auto_activate: v })} /></div>
        <Field label="Длительность, дней"><input className={inputClass} inputMode="numeric" value={String(t.days)} onChange={(e) => setTrial({ ...t, days: Number(e.target.value.replace(/\D/g, "")) })} /></Field>
        <Button className="h-10 w-full" onClick={() => put.mutate({ key: "trial", value: t })}>Сохранить</Button>
      </Card>
      <Card className="space-y-3 p-4">
        <p className="font-semibold">Реферальная программа</p>
        <div className="flex items-center justify-between text-sm"><span>Включена</span><Toggle checked={!!r.enabled} onChange={(v) => setRef({ ...r, enabled: v })} /></div>
        {([["registration_reward_searches", "Пригласившему за регистрацию"], ["first_purchase_reward_searches", "Пригласившему за первую покупку"], ["invitee_bonus_searches", "Приглашённому"]] as const).map(([k, l]) => (
          <Field key={k} label={`${l}, поисков`}><input className={inputClass} inputMode="numeric" value={String(r[k])} onChange={(e) => setRef({ ...r, [k]: Number(e.target.value.replace(/\D/g, "")) })} /></Field>
        ))}
        <Button className="h-10 w-full" onClick={() => put.mutate({ key: "referral", value: r })}>Сохранить</Button>
      </Card>
      {put.error && <p className="text-sm text-bad">{(put.error as Error).message}</p>}
    </div>
  );
}

function Payments() {
  const qc = useQueryClient();
  const p = useQuery({ queryKey: ["admin", "payments"], queryFn: () => api.get<(Payment & { user_id: number; telegram_payment_charge_id: string })[]>("/api/v1/admin/payments") });
  const refund = useMutation({ mutationFn: (id: number) => api.post(`/api/v1/admin/payments/${id}/refund`), onSuccess: () => { haptic.success(); qc.invalidateQueries({ queryKey: ["admin"] }); } });
  if (!p.data) return <Skeleton className="h-64 rounded-[20px]" />;
  if (!p.data.length) return <p className="rounded-2xl bg-surface-2 p-5 text-center text-sm text-ink-2">Транзакций пока нет</p>;
  return (
    <div className="space-y-3">
      {refund.error && <p className="text-sm text-bad">{(refund.error as Error).message}</p>}
      <ul className="divide-y divide-line overflow-hidden rounded-[20px] bg-surface ring-1 ring-line">
        {p.data.map((x) => (
          <li key={x.id} className="flex items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-[14px] font-medium uppercase">{x.plan_code} · <span className="font-mono">{x.amount_stars} ⭐</span>{x.is_recurring && " · рек."}</p>
              <p className="truncate font-mono text-[11px] text-ink-3">user {x.user_id} · {date(x.created_at, true)} · {x.telegram_payment_charge_id}</p>
            </div>
            {x.status === "refunded" ? <Badge tone="bad">возврат</Badge> : (
              <button className="text-[13px] text-bad" onClick={async () => { if (await confirm(`Вернуть ${x.amount_stars} ⭐ и отключить подписку?`)) refund.mutate(x.id); }}>Возврат</button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface Integrations {
  marketplaces: { code: string; name: string; kind: string; enabled: boolean; state: string; note: string; last_check_at: string | null; last_error: string | null; latency_ms: number | null }[];
  ai: Record<string, { provider: string; model?: string; dim?: number; ok: number; fail: number; last_ok: string | null; last_error: string | null }>;
}
const KIND_LABEL: Record<string, string> = { official_api: "официальный API", affiliate_api: "партнёрский API", partner_feed: "партнёрский фид", web_search: "Lens + веб-поиск", none: "нет API" };
const STATE_TONE: Record<string, "good" | "bad" | "neutral" | "accent"> = { active: "good", down: "bad", not_configured: "accent", no_legal_api: "neutral", disabled: "neutral" };
const STATE_LABEL: Record<string, string> = { active: "работает", down: "недоступен", not_configured: "нет ключей/фида", no_legal_api: "нет легального API", disabled: "выключен" };

function IntegrationsView() {
  const q = useQuery({ queryKey: ["admin", "integrations"], queryFn: () => api.get<Integrations>("/api/v1/admin/integrations"), refetchInterval: 30000 });
  if (!q.data) return <Skeleton className="h-64 rounded-[20px]" />;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {Object.entries(q.data.ai).map(([k, v]) => (
          <Card key={k} className="p-4">
            <p className="text-[12px] text-ink-3">{k === "vision" ? "Анализ фото" : "Эмбеддинги"}</p>
            <p className="mt-1 text-[14px] font-medium">{v.provider}{v.model ? ` · ${v.model}` : ""}</p>
            <p className="mt-1 font-mono text-[12px]"><span className="text-good">{v.ok} ok</span> · <span className="text-bad">{v.fail} fail</span></p>
            {v.last_error && <p className="mt-1 line-clamp-2 text-[11px] text-ink-3">{v.last_error.split("|")[1]}</p>}
          </Card>
        ))}
      </div>
      <ul className="space-y-3">
        {q.data.marketplaces.map((m) => (
          <Card key={m.code} className="p-4">
            <div className="flex items-center justify-between">
              <p className="font-semibold">{m.name} <span className="text-xs font-normal text-ink-3">{KIND_LABEL[m.kind] ?? m.kind}</span></p>
              <Badge tone={m.enabled ? STATE_TONE[m.state] ?? "neutral" : "neutral"}>{m.enabled ? STATE_LABEL[m.state] ?? m.state : "выключен"}</Badge>
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{m.note}</p>
            {(m.last_check_at || m.last_error) && (
              <p className="mt-2 font-mono text-[11px] text-ink-3">{m.last_check_at && `проверка ${date(m.last_check_at, true)}`}{m.latency_ms !== null && ` · ${m.latency_ms} мс`}{m.last_error && ` · ${m.last_error}`}</p>
            )}
          </Card>
        ))}
      </ul>
    </div>
  );
}

function Errors() {
  const q = useQuery({ queryKey: ["admin", "errors"], queryFn: () => api.get<{ ts: number; service: string; logger: string; msg: string; exc: string | null }[]>("/api/v1/admin/errors"), refetchInterval: 20000 });
  if (!q.data) return <Skeleton className="h-64 rounded-[20px]" />;
  if (!q.data.length) return <p className="rounded-2xl bg-surface-2 p-5 text-center text-sm text-ink-2">Ошибок нет</p>;
  return (
    <ul className="space-y-2">
      {q.data.map((e, i) => (
        <details key={i} className="rounded-2xl bg-surface p-3 ring-1 ring-line">
          <summary className="cursor-pointer list-none">
            <p className="font-mono text-[11px] text-ink-3">{new Date(e.ts * 1000).toLocaleString("ru-RU")} · {e.service} · {e.logger}</p>
            <p className="mt-0.5 text-[13px]">{e.msg}</p>
          </summary>
          {e.exc && <pre className="mt-2 max-h-60 overflow-auto rounded-xl bg-surface-2 p-2 text-[10px] leading-snug">{e.exc}</pre>}
        </details>
      ))}
    </ul>
  );
}

export default function Admin() {
  const { data: me, isLoading } = useMe();
  if (isLoading) return <Skeleton className="m-5 h-64" />;
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader label="XIII — Админ" title="Админ-панель" serif={false} />
      <div className="px-4">
        <Tabs />
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="users" element={<Users />} />
          <Route path="users/:id" element={<UserDetail />} />
          <Route path="plans" element={<Plans />} />
          <Route path="settings" element={<AppSettings />} />
          <Route path="payments" element={<Payments />} />
          <Route path="integrations" element={<IntegrationsView />} />
          <Route path="errors" element={<Errors />} />
        </Routes>
      </div>
    </div>
  );
}
