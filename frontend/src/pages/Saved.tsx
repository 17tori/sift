import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { IconBell, IconHeart, IconLock } from "../components/icons";
import { ProductCard } from "../components/ProductCard";
import { Button, Empty, ErrorView, PageHeader, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { money } from "../lib/format";
import { useFavorites, useMe, useToggleFavorite } from "../lib/queries";
import { useUi } from "../lib/store";
import { haptic } from "../lib/telegram";

export default function Saved() {
  const favs = useFavorites();
  const { data: me } = useMe();
  const { view } = useUi();
  const toggle = useToggleFavorite();
  const qc = useQueryClient();
  const nav = useNavigate();
  const alerts = !!me?.plan.features.price_alerts;
  const alert = useMutation({
    mutationFn: ({ id, on }: { id: number; on: boolean }) => api.patch(`/api/v1/favorites/${id}`, { price_alert: on }),
    onSuccess: () => { haptic.success(); qc.invalidateQueries({ queryKey: ["favorites"] }); },
  });

  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader numeral="VI" label="Фонды" title="Моя *коллекция*" right={favs.data ? <span className="caption text-ink-2"><span className="font-semibold text-ink">{favs.data.length}</span> экспонатов</span> : undefined} />
      {!alerts && favs.data && favs.data.length > 0 && (
        <button onClick={() => nav("/subscription")} className="mx-5 mb-5 flex w-[calc(100%-2.5rem)] items-center gap-3 border-y border-line py-3.5 text-left text-[14px] text-ink">
          <IconLock size={16} /> Уведомления о снижении цены доступны в ULTRA
        </button>
      )}
      <div className="px-5">
        {favs.isLoading ? (
          <div className="grid grid-cols-2 gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="aspect-[4/6] rounded-[20px]" />)}</div>
        ) : favs.isError ? (
          <ErrorView error={favs.error} retry={() => favs.refetch()} />
        ) : !favs.data?.length ? (
          <Empty icon={<IconHeart size={26} />} title="Фонды *пусты*" text="Сохраняйте понравившиеся находки сердечком на карточке, чтобы вернуться к ним позже."
            action={<Link to="/"><Button>Найти вещь</Button></Link>} />
        ) : (
          <div className={view === "grid" ? "grid grid-cols-2 gap-x-3 gap-y-6" : "flex flex-col"}>
            {favs.data.map((f, i) => (
              <div key={f.id} className="relative">
                <ProductCard p={f.product} view={view} frame="arch" index={i} previousPrice={alerts ? f.saved_price : null} previousCurrency={f.saved_currency}
                  onFavorite={(on) => toggle.mutate({ productId: f.product.product_id, on })} />
                <div className="mt-1.5 flex items-center justify-between px-1">
                  <span className="font-mono text-[11px] text-ink-3">сохр. {money(f.saved_price, f.saved_currency)}</span>
                  {alerts && (
                    <button onClick={() => alert.mutate({ id: f.id, on: !f.price_alert })}
                      className={f.price_alert ? "text-accent" : "text-ink-3"} aria-label="Уведомлять о снижении цены">
                      <IconBell size={17} filled={f.price_alert} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
