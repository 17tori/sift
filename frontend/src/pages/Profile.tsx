import { useNavigate } from "react-router-dom";
import { IconBell, IconChat, IconGift, IconSettings, IconShield, IconSpark, IconStar } from "../components/icons";
import { Badge, Card, ErrorView, PageHeader, Row, Skeleton } from "../components/ui";
import { date, num, timeLeft } from "../lib/format";
import { useMe } from "../lib/queries";

export default function Profile() {
  const { data: me, isLoading, error, refetch } = useMe();
  const nav = useNavigate();
  if (error) return <ErrorView error={error} retry={() => refetch()} />;
  if (isLoading || !me) return <div className="space-y-4 p-5"><Skeleton className="h-24" /><Skeleton className="h-40" /><Skeleton className="h-60" /></div>;
  const pct = me.quota.limit ? Math.min(100, (me.quota.used / me.quota.limit) * 100) : 0;
  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader numeral="VIII" label="Хранитель" title="Профиль" />
      <div className="space-y-4 px-4">
        <Card className="flex items-center gap-4 p-4">
          {me.photo_url ? <img src={me.photo_url} alt="" className="h-14 w-14 rounded-2xl object-cover" />
            : <div className="grid h-14 w-14 place-items-center rounded-2xl bg-ink font-display text-xl font-bold text-bg">{me.first_name.slice(0, 1)}</div>}
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-lg font-semibold">{me.first_name}</p>
            <p className="text-xs text-ink-3">{me.username ? `@${me.username} · ` : ""}с {date(me.created_at)}</p>
          </div>
          <Badge tone={me.plan.code === "free" ? "neutral" : "accent"}>{me.plan.title}</Badge>
        </Card>

        <Card className="p-4">
          <div className="flex items-baseline justify-between">
            <p className="text-sm text-ink-2">Поиски {me.quota.window === "day" ? "сегодня" : "в периоде"}</p>
            <p className="font-mono text-sm"><span className="text-ink">{me.quota.used}</span><span className="text-ink-3"> / {me.quota.limit}</span></p>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-3 flex justify-between text-xs text-ink-3">
            <span>Обновится через {timeLeft(me.quota.resets_at)}</span>
            {me.quota.bonus > 0 && <span>+{me.quota.bonus} бонусных</span>}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4">
            <div><p className="font-mono text-xl">{num(me.total_searches)}</p><p className="text-xs text-ink-3">всего поисков</p></div>
            <div><p className="font-mono text-xl">{num(me.favorites_count)}</p><p className="text-xs text-ink-3">в избранном</p></div>
          </div>
          {me.subscription && (
            <p className="mt-4 border-t border-line pt-3 text-xs text-ink-2">
              {me.trial.active ? "Пробный период" : "Подписка"} до {date(me.subscription.expires_at)}
              {me.subscription.is_recurring && (me.subscription.auto_renew ? " · автопродление включено" : " · автопродление выключено")}
            </p>
          )}
        </Card>

        <Card className="divide-y divide-line overflow-hidden">
          <Row icon={<IconSpark size={18} />} title="Подписка" value={me.plan.title} onClick={() => nav("/subscription")} />
          <Row icon={<IconStar size={18} />} title="История платежей" onClick={() => nav("/subscription#payments")} />
          <Row icon={<IconBell size={18} />} title="Наблюдение за вещами" value={me.plan.features.watch_limit ? undefined : "ULTRA"} onClick={() => nav("/saved?tab=watch")} />
          <Row icon={<IconGift size={18} />} title="Подарить поиски" value="⭐" onClick={() => nav("/gifts")} />
          <Row icon={<IconGift size={18} />} title="Пригласить друзей" onClick={() => nav("/referral")} />
          <Row icon={<IconSettings size={18} />} title="Настройки" onClick={() => nav("/settings")} />
          <Row icon={<IconChat size={18} />} title="Поддержка" onClick={() => nav("/support")} />
          {me.is_admin && <Row icon={<IconShield size={18} />} title="Админ-панель" onClick={() => nav("/admin")} />}
        </Card>
        <p className="px-1 text-center font-mono text-[11px] text-ink-3">Telegram ID {me.telegram_id}</p>
      </div>
    </div>
  );
}
