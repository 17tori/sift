import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { IconCopy, IconGift } from "../components/icons";
import { Button, Card, ErrorView, PageHeader, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { haptic, openTelegram } from "../lib/telegram";
import type { Referral as R } from "../lib/types";

export default function Referral() {
  const q = useQuery({ queryKey: ["referral"], queryFn: () => api.get<R>("/api/v1/referrals") });
  const [copied, setCopied] = useState(false);
  if (q.isError) return <ErrorView error={q.error} retry={() => q.refetch()} />;
  const r = q.data;
  const copy = async () => {
    if (!r) return;
    try { await navigator.clipboard.writeText(r.link); setCopied(true); haptic.success(); setTimeout(() => setCopied(false), 1800); } catch { /* unsupported */ }
  };
  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader title="Пригласить друзей" subtitle="Бонусные поиски за каждого друга" />
      <div className="space-y-4 px-4">
        {!r ? <Skeleton className="h-64 rounded-[20px]" /> : (
          <>
            <Card className="p-5">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent text-white"><IconGift size={24} /></span>
              <ul className="mt-4 space-y-2 text-[14px]">
                <li><span className="font-mono text-accent">+{r.reward_registration}</span> поисков вам за каждого нового друга</li>
                <li><span className="font-mono text-accent">+{r.reward_first_purchase}</span> поисков, когда друг оформит подписку</li>
                <li><span className="font-mono text-accent">+{r.invitee_bonus}</span> поисков другу при регистрации</li>
              </ul>
              <div className="mt-5 flex items-center gap-2 rounded-2xl bg-surface-2 p-1.5 pl-4">
                <span className="flex-1 truncate font-mono text-[13px] text-ink-2">{r.link || r.code}</span>
                <button onClick={copy} className="flex h-9 items-center gap-1.5 rounded-xl bg-surface px-3 text-[13px] ring-1 ring-line"><IconCopy size={15} />{copied ? "Готово" : "Копировать"}</button>
              </div>
              {r.link && (
                <Button className="mt-3 w-full" onClick={() => openTelegram(`https://t.me/share/url?url=${encodeURIComponent(r.link)}&text=${encodeURIComponent("Нахожу вещи по фото на всех маркетплейсах")}`)}>
                  Поделиться
                </Button>
              )}
            </Card>
            <div className="grid grid-cols-3 gap-3">
              {[["Приглашено", r.invited], ["Купили", r.purchased], ["Получено", r.earned_searches]].map(([l, v]) => (
                <Card key={l as string} className="p-4"><p className="font-mono text-2xl">{v}</p><p className="text-xs text-ink-3">{l}</p></Card>
              ))}
            </div>
            <p className="px-1 text-xs text-ink-3">Бонус начисляется только за новых пользователей и только один раз. Пригласить самого себя нельзя.</p>
          </>
        )}
      </div>
    </div>
  );
}
