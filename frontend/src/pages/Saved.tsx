import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Arch, CountUp, Photo } from "../components/archive";
import { CollectionPicker } from "../components/CollectionPicker";
import { IconBell, IconHanger, IconHeart, IconLock, IconTrash } from "../components/icons";
import { ProductCard } from "../components/ProductCard";
import { Button, cx, Empty, ErrorView, inputClass, PageHeader, Segmented, Sheet, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { money, plural, relative } from "../lib/format";
import { cardVariants, rowVariants, spring } from "../lib/motion";
import { useCollections, useFavorites, useMe, useToggleFavorite, useWatches, useWatchToggle } from "../lib/queries";
import { useUi } from "../lib/store";
import { confirm, haptic } from "../lib/telegram";
import { toast } from "../lib/toast";
import type { Collection, Favorite } from "../lib/types";

type Tab = "finds" | "watch";

/** Collection shelf: arch covers, the active one outlined in ink. */
function Shelf({ items, total, cover, active, onPick, onAdd }: {
  items: Collection[]; total: number; cover: string | null; active: number | null; onPick: (id: number | null) => void; onAdd: () => void;
}) {
  const tile = (key: string, id: number | null, title: string, count: number | null, cover: string | null, i: number) => (
    <motion.button key={key} custom={i} variants={cardVariants} initial="hidden" animate="show" whileTap={{ scale: 0.95 }}
      onClick={() => { haptic.select(); onPick(id); }}
      className="flex w-[76px] shrink-0 flex-col items-center gap-1.5">
      <Arch className="h-[92px] w-[70px]" outlineClass={active === id ? "text-ink" : "text-line-strong"}>
        {cover ? <Photo src={cover} alt="" /> : <div className="grid h-full w-full place-items-center bg-surface-2 font-serif text-[26px] text-ink-3">{title.slice(0, 1)}</div>}
      </Arch>
      <span className={cx("w-full truncate text-center text-[12px]", active === id ? "font-semibold text-ink" : "text-ink-2")}>{title}</span>
      {count !== null && <span className="-mt-1 font-mono text-[10px] text-ink-3">{count}</span>}
      {active === id && <motion.span layoutId="shelf-dot" className="h-1 w-1 rounded-full bg-accent" transition={spring.soft} />}
    </motion.button>
  );
  return (
    <div className="-mx-5 mb-5 flex gap-2 overflow-x-auto px-5 pb-1 [scrollbar-width:none]">
      {tile("all", null, "Все", total, cover, 0)}
      {items.map((c, i) => tile(String(c.id), c.id, c.title, c.count, c.cover_url, i + 1))}
      <motion.button custom={items.length + 1} variants={cardVariants} initial="hidden" animate="show" whileTap={{ scale: 0.95 }}
        onClick={() => { haptic.tap(); onAdd(); }} className="flex w-[76px] shrink-0 flex-col items-center gap-1.5">
        <Arch className="h-[92px] w-[70px]" dashed>
          <div className="grid h-full w-full place-items-center text-[26px] font-light text-ink-3">+</div>
        </Arch>
        <span className="text-[12px] text-ink-3">Новая</span>
      </motion.button>
    </div>
  );
}

function TitleSheet({ open, onClose, initial, title, onSubmit, pending }: {
  open: boolean; onClose: () => void; initial: string; title: string; onSubmit: (t: string) => void; pending: boolean;
}) {
  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <TitleForm key={String(open) + initial} initial={initial} onSubmit={onSubmit} pending={pending} />
    </Sheet>
  );
}

function TitleForm({ initial, onSubmit, pending }: { initial: string; onSubmit: (t: string) => void; pending: boolean }) {
  const [v, setV] = useState(initial);
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (v.trim()) onSubmit(v.trim()); }}>
      <input autoFocus className={inputClass} maxLength={64} value={v} placeholder="Например, «Осень» или «Подарки»" onChange={(e) => setV(e.target.value)} />
      <Button type="submit" className="w-full" loading={pending} disabled={!v.trim()}>Сохранить</Button>
    </form>
  );
}

function Finds() {
  const favs = useFavorites();
  const cols = useCollections();
  const { data: me } = useMe();
  const { view } = useUi();
  const toggle = useToggleFavorite();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [active, setActive] = useState<number | null>(null);
  const [moving, setMoving] = useState<Favorite | null>(null);
  const [edit, setEdit] = useState<"new" | "rename" | null>(null);
  const alerts = !!me?.plan.features.price_alerts;
  const alert = useMutation({
    mutationFn: ({ id, on }: { id: number; on: boolean }) => api.patch(`/api/v1/favorites/${id}`, { price_alert: on }),
    onSuccess: () => { haptic.success(); qc.invalidateQueries({ queryKey: ["favorites"] }); },
  });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["collections"] }); qc.invalidateQueries({ queryKey: ["favorites"] }); };
  const save = useMutation({
    mutationFn: (t: string) => edit === "rename" && active !== null
      ? api.patch<Collection>(`/api/v1/collections/${active}`, { title: t })
      : api.post<Collection>("/api/v1/collections", { title: t }),
    onSuccess: (c) => { haptic.success(); setEdit(null); setActive(c.id); refresh(); },
    onError: (e) => toast((e as Error).message, "bad"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/v1/collections/${id}`),
    onSuccess: () => { setActive(null); refresh(); toast("Коллекция удалена, находки остались в избранном"); },
  });
  const current = cols.data?.find((c) => c.id === active);
  const list = (favs.data ?? []).filter((f) => active === null || f.collection_id === active);

  if (favs.isLoading) return <div className="grid grid-cols-2 gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="aspect-[4/6] rounded-[20px]" />)}</div>;
  if (favs.isError) return <ErrorView error={favs.error} retry={() => favs.refetch()} />;
  if (!favs.data?.length) {
    return <Empty icon={<IconHeart size={26} />} title="Фонды *пусты*" text="Сохраняйте понравившиеся находки сердечком на карточке, чтобы вернуться к ним позже."
      action={<Link to="/"><Button>Найти вещь</Button></Link>} />;
  }
  return (
    <>
      {!alerts && (
        <button onClick={() => nav("/subscription")} className="mb-5 flex w-full items-center gap-3 border-y border-line py-3.5 text-left text-[14px] text-ink">
          <IconLock size={16} /> Уведомления о снижении цены доступны в ULTRA
        </button>
      )}
      <Shelf items={cols.data ?? []} total={favs.data.length} cover={favs.data[0]?.product.image_url ?? null} active={active} onPick={setActive} onAdd={() => setEdit("new")} />
      <AnimatePresence mode="popLayout">
        {current && (
          <motion.div key={current.id} className="mb-5 flex items-center gap-3" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <h2 className="flex-1 truncate font-serif text-[28px] leading-8 font-light italic">{current.title}</h2>
            <button className="caption text-ink-2" onClick={() => setEdit("rename")}>Переименовать</button>
            <button className="grid h-8 w-8 place-items-center text-ink-3" aria-label="Удалить коллекцию"
              onClick={async () => { if (await confirm(`Удалить коллекцию «${current.title}»? Находки останутся в избранном.`)) remove.mutate(current.id); }}>
              <IconTrash size={17} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
      {list.length === 0 ? (
        <Empty title="Здесь *пока пусто*" text="Откройте находку и нажмите «В коллекцию», или используйте значок вешалки под карточкой." />
      ) : (
        <LayoutGroup>
          <motion.div layout className={view === "grid" ? "grid grid-cols-2 gap-x-3 gap-y-6" : "flex flex-col"}>
            <AnimatePresence initial={false} mode="popLayout">
              {list.map((f, i) => (
                <motion.div key={f.id} layout className="relative" exit={{ opacity: 0, scale: 0.96 }} transition={spring.soft}>
                  <ProductCard p={f.product} view={view} frame="arch" index={i} previousPrice={alerts ? f.saved_price : null} previousCurrency={f.saved_currency}
                    onOpen={f.search_id ? () => nav(`/search/${f.search_id}/item/${f.product.product_id}`) : undefined}
                    onFavorite={(on) => toggle.mutate({ productId: f.product.product_id, on })} />
                  <div className="mt-1.5 flex items-center justify-between gap-2 px-1">
                    <span className="font-mono text-[11px] text-ink-3">сохр. {money(f.saved_price, f.saved_currency)}</span>
                    <span className="flex items-center gap-2.5">
                      <button onClick={() => setMoving(f)} aria-label="В коллекцию" className={f.collection_id ? "text-ink" : "text-ink-3"}>
                        <IconHanger size={17} />
                      </button>
                      {alerts && (
                        <button onClick={() => alert.mutate({ id: f.id, on: !f.price_alert })}
                          className={f.price_alert ? "text-accent" : "text-ink-3"} aria-label="Уведомлять о снижении цены">
                          <IconBell size={17} filled={f.price_alert} />
                        </button>
                      )}
                    </span>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        </LayoutGroup>
      )}
      <CollectionPicker open={!!moving} onClose={() => setMoving(null)} favoriteId={moving?.id ?? null}
        productId={moving?.product.product_id ?? 0} current={moving?.collection_id ?? null} />
      <TitleSheet open={edit !== null} onClose={() => setEdit(null)} pending={save.isPending}
        title={edit === "rename" ? "Переименовать" : "Новая коллекция"} initial={edit === "rename" ? current?.title ?? "" : ""}
        onSubmit={(t) => save.mutate(t)} />
    </>
  );
}

function WatchList() {
  const w = useWatches();
  const { data: me } = useMe();
  const stop = useWatchToggle();
  const nav = useNavigate();
  const limit = me?.plan.features.watch_limit ?? 0;
  if (w.isLoading) return <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}</div>;
  if (w.isError) return <ErrorView error={w.error} retry={() => w.refetch()} />;
  if (limit <= 0) {
    return <Empty title="Наблюдение *в ULTRA*"
      text="Раз в день SIFT заново ищет вещь по вашему фото и пишет в чат, когда она появится дешевле или на новой площадке."
      action={<Button onClick={() => nav("/subscription")}><IconLock size={16} /> Открыть ULTRA</Button>} />;
  }
  const items = w.data?.items ?? [];
  if (!items.length) {
    return <Empty title="Пока *не следите*"
      text="Откройте завершённый поиск и нажмите «Следить за ценой». Повторные поиски не тратят лимит."
      action={<Link to="/history"><Button variant="secondary">Мои поиски</Button></Link>} />;
  }
  return (
    <>
      <p className="caption mb-3 text-ink-3">
        <CountUp value={items.length} className="text-ink" /> из {limit} · проверка раз в сутки
      </p>
      <ul className="border-t border-line">
        <AnimatePresence initial={false}>
          {items.map((x, i) => (
            <motion.li key={x.id} custom={i} variants={rowVariants} initial="hidden" animate="show" exit={{ opacity: 0, x: 24 }} layout
              className="flex items-center gap-3.5 border-b border-line py-3">
              <button className="flex min-w-0 flex-1 items-center gap-3.5 text-left" onClick={() => nav(`/search/${x.last_search_id ?? x.search_id}`)}>
                <Arch className="h-[78px] w-[60px] shrink-0"><Photo src={x.image_url} alt="" /></Arch>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium">{x.title ?? "Вещь"}</span>
                  <span className="mt-1 block font-mono text-[13px] tnum">
                    {x.best_price ? <>лучшая {money(x.best_price, x.best_currency)}</> : <span className="text-ink-3">цены пока нет</span>}
                  </span>
                  <span className="caption mt-1 block text-ink-3">
                    {x.runs ? `${x.runs} ${plural(x.runs, "проверка", "проверки", "проверок")}` : "первая проверка в течение суток"}
                    {x.last_found_at ? ` · нашлось ${relative(x.last_found_at)}` : ""}
                  </span>
                </span>
              </button>
              <button className="grid h-9 w-9 place-items-center rounded-full text-ink-3 shadow-[inset_0_0_0_1px_var(--line)]" aria-label="Перестать следить"
                onClick={async () => { if (await confirm("Перестать следить за этой вещью?")) stop.mutate({ searchId: x.search_id, on: false }); }}>
                <IconTrash size={16} />
              </button>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </>
  );
}

export default function Saved() {
  const favs = useFavorites();
  const watches = useWatches();
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "watch" ? "watch" : "finds";
  const n = favs.data?.length;
  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader numeral="VI" label="Фонды" title="Моя *коллекция*"
        right={n !== undefined ? <span className="caption text-ink-2"><span className="font-semibold text-ink">{n}</span> {plural(n, "экспонат", "экспоната", "экспонатов")}</span> : undefined} />
      <div className="px-5">
        <div className="mb-5">
          <Segmented<Tab> value={tab} onChange={(v) => setParams(v === "watch" ? { tab: "watch" } : {}, { replace: true })} options={[
            { value: "finds", label: "Находки" },
            { value: "watch", label: <>Наблюдение{watches.data?.items.length ? <span className="font-mono text-[11px] text-ink-3"> {watches.data.items.length}</span> : null}</> },
          ]} />
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={tab} initial={{ opacity: 0, x: tab === "watch" ? 16 : -16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.24 }}>
            {tab === "finds" ? <Finds /> : <WatchList />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
