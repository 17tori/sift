import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { IconCheck, IconClose, IconFilter, IconGrid, IconList, IconLock, IconRefresh, IconSearch } from "../components/icons";
import { ProductCard, ProductSkeleton } from "../components/ProductCard";
import { Button, Chip, cx, Empty, ErrorView, Field, inputClass, Segmented, Sheet, Spinner } from "../components/ui";
import { api, qs } from "../lib/api";
import { CATEGORY_LABEL, CONDITION_LABEL, ERROR_LABEL, MODE_LABEL } from "../lib/format";
import { useConfig, useMe, useToggleFavorite } from "../lib/queries";
import { EMPTY_FILTERS, type ResultFilters, useUi } from "../lib/store";
import { haptic } from "../lib/telegram";
import type { Results, Search } from "../lib/types";

const STAGES: { key: Search["stage"]; label: string }[] = [
  { key: "uploaded", label: "Фото загружено" },
  { key: "analyzing", label: "Анализ изображения и категории" },
  { key: "embedding", label: "Визуальные характеристики" },
  { key: "searching", label: "Поиск по маркетплейсам" },
  { key: "ranking", label: "Сопоставление и сортировка" },
];
const ORDER = ["uploaded", "analyzing", "embedding", "searching", "ranking", "done"];

const PROVIDER_STATE: Record<string, string> = {
  searching: "ищем…", done: "", error: "ошибка", timeout: "не ответил", unavailable: "не подключён", skipped: "пропущен",
};

function Stages({ s }: { s: Search }) {
  const cur = ORDER.indexOf(s.stage);
  // analyzing and embedding run concurrently in the worker
  const idx = (k: string) => (k === "embedding" && s.stage === "analyzing" ? cur : ORDER.indexOf(k));
  return (
    <ol className="space-y-3">
      {STAGES.map((st) => {
        const i = idx(st.key);
        const done = s.status !== "failed" && (cur > i || s.status === "completed");
        const now = !done && cur === i && s.status !== "failed";
        return (
          <li key={st.key} className="flex items-center gap-3">
            <span className={cx("grid h-6 w-6 place-items-center rounded-full text-white transition-colors",
              done ? "bg-ink text-bg" : now ? "bg-accent" : "bg-surface-2")}>
              {done ? <IconCheck size={14} className="text-bg" /> : now ? <Spinner size={13} /> : null}
            </span>
            <span className={cx("text-[14px]", done || now ? "text-ink" : "text-ink-3")}>{st.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function ProviderChips({ s, names }: { s: Search; names: Record<string, string> }) {
  const entries = Object.entries(s.providers);
  if (!entries.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([code, st]) => (
        <span key={code} className={cx("inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[12px]",
          st.state === "done" ? "bg-surface-2 text-ink" : st.state === "searching" ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-3")}>
          {st.state === "searching" && <Spinner size={11} />}
          {names[code] ?? code}
          {st.state === "done" ? <span className="font-mono text-ink-2">{st.count ?? 0}</span> : <span>{PROVIDER_STATE[st.state]}</span>}
        </span>
      ))}
    </div>
  );
}

function AnalysisSummary({ s }: { s: Search }) {
  const a = s.analysis;
  if (!a || a.vision_error) return null;
  const tags = [a.category && CATEGORY_LABEL[a.category], a.material, a.pattern, a.silhouette, ...(a.style ?? []).slice(0, 2)].filter(Boolean) as string[];
  return (
    <div className="mt-4">
      <p className="font-display text-[19px] leading-tight font-semibold">{a.title_ru || a.title_en}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {(a.colors ?? []).map((c) => (
          <span key={c.hex + c.name} className="inline-flex h-6 items-center gap-1.5 rounded-full bg-surface-2 px-2 text-[11px] text-ink-2">
            <span className="h-3 w-3 rounded-full ring-1 ring-line-strong" style={{ background: c.hex }} />{c.name}
          </span>
        ))}
        {tags.map((t) => <span key={t} className="h-6 rounded-full bg-surface-2 px-2 text-[11px] leading-6 text-ink-2">{t}</span>)}
        {a.brand?.name && a.brand.confidence !== "none" && (
          <span className="h-6 rounded-full bg-accent-soft px-2 text-[11px] leading-6 text-accent">
            Бренд: {a.brand.name} ({a.brand.confidence === "high" ? "уверенно" : "предположительно"})
          </span>
        )}
      </div>
    </div>
  );
}

function FiltersSheet({ open, onClose, value, onApply, facets, locked, names, categories }: {
  open: boolean; onClose: () => void; value: ResultFilters; onApply: (f: ResultFilters) => void;
  facets: Results["facets"] | undefined; locked: boolean; names: Record<string, string>; categories: string[];
}) {
  const [f, setF] = useState(value);
  const nav = useNavigate();
  useEffect(() => { if (open) setF(value); }, [open, value]);
  const set = (p: Partial<ResultFilters>) => setF((x) => ({ ...x, ...p }));
  const lockHint = locked && (
    <button onClick={() => nav("/subscription")} className="mb-4 flex w-full items-center gap-2 rounded-2xl bg-accent-soft px-4 py-3 text-left text-[13px] text-accent">
      <IconLock size={16} /> Расширенные фильтры доступны в PRO и ULTRA
    </button>
  );
  return (
    <Sheet open={open} onClose={onClose} title="Фильтры">
      <div className="space-y-5">
        <Field label="Маркетплейс">
          <div className="flex flex-wrap gap-2">
            {(facets?.marketplace ?? []).map((m) => (
              <Chip key={m.value} active={f.marketplace.includes(m.value)}
                onClick={() => set({ marketplace: f.marketplace.includes(m.value) ? f.marketplace.filter((x) => x !== m.value) : [...f.marketplace, m.value] })}>
                {names[m.value] ?? m.value} <span className="font-mono opacity-60">{m.count}</span>
              </Chip>
            ))}
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Цена от"><input inputMode="decimal" className={inputClass} value={f.price_min} onChange={(e) => set({ price_min: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
          <Field label="Цена до"><input inputMode="decimal" className={inputClass} value={f.price_max} onChange={(e) => set({ price_max: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
        </div>
        <Field label="Сортировка">
          <Segmented value={f.sort} onChange={(sort) => set({ sort })} options={[
            { value: "relevance", label: "Лучшие" }, { value: "similarity", label: "Сходство" },
            { value: "price_asc", label: "Цена ↑" }, { value: "price_desc", label: "Цена ↓" }]} />
        </Field>
        {lockHint}
        <fieldset disabled={locked} className={cx("space-y-5", locked && "opacity-50")}>
          <Field label="Состояние">
            <div className="flex flex-wrap gap-2">
              {["", "new", "used"].map((c) => <Chip key={c} active={f.condition === c} onClick={() => !locked && set({ condition: c })}>{c ? CONDITION_LABEL[c] : "Любое"}</Chip>)}
            </div>
          </Field>
          <Field label="Категория">
            <select className={inputClass} value={f.category} onChange={(e) => set({ category: e.target.value })}>
              <option value="">Любая</option>
              {categories.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] ?? c}</option>)}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Цвет"><input className={inputClass} placeholder="чёрный" value={f.color} onChange={(e) => set({ color: e.target.value })} /></Field>
            <Field label="Размер"><input className={inputClass} placeholder="M, 38" value={f.size} onChange={(e) => set({ size: e.target.value })} /></Field>
          </div>
          <Field label="Страна продавца">
            <div className="flex flex-wrap gap-2">
              <Chip active={!f.country} onClick={() => set({ country: "" })}>Любая</Chip>
              {(facets?.country ?? []).map((c) => <Chip key={c.value} active={f.country === c.value} onClick={() => set({ country: c.value })}>{c.value}</Chip>)}
            </div>
          </Field>
        </fieldset>
        <div className="grid grid-cols-2 gap-3 pt-2">
          <Button variant="secondary" onClick={() => setF({ ...EMPTY_FILTERS })}>Сбросить</Button>
          <Button onClick={() => { onApply(f); onClose(); }}>Показать</Button>
        </div>
      </div>
    </Sheet>
  );
}

export default function SearchPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const { data: cfg } = useConfig();
  const { data: me } = useMe();
  const { view, setView, filters, setFilters, setActiveSearch } = useUi();
  const f = filters[id] ?? EMPTY_FILTERS;
  const [sheet, setSheet] = useState(false);
  const fav = useToggleFavorite();
  const names = useMemo(() => Object.fromEntries((cfg?.marketplaces ?? []).map((m) => [m.code, m.name])), [cfg]);

  const search = useQuery({
    queryKey: ["search", id],
    queryFn: () => api.get<Search>(`/api/v1/searches/${id}`),
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.status) ? 1200 : false),
  });
  const s = search.data;
  const live = !!s && ["queued", "running"].includes(s.status);
  useEffect(() => { if (s && !live) { setActiveSearch(null); qc.invalidateQueries({ queryKey: ["me"] }); } }, [live, s, setActiveSearch, qc]);

  const params = {
    marketplace: f.marketplace.join(","), price_min: f.price_min, price_max: f.price_max, condition: f.condition,
    country: f.country, category: f.category, color: f.color, size: f.size, sort: f.sort,
  };
  const results = useInfiniteQuery({
    queryKey: ["results", id, params, s?.results_count, s?.status],
    enabled: !!s && s.results_count > 0,
    initialPageParam: 0,
    queryFn: ({ pageParam }) => api.get<Results>(`/api/v1/searches/${id}/results${qs({ ...params, offset: pageParam, limit: 24 })}`),
    getNextPageParam: (last) => last.next_offset ?? undefined,
    placeholderData: (prev) => prev,
  });
  const items = results.data?.pages.flatMap((p) => p.items) ?? [];
  const first = results.data?.pages[0];

  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((e) => { if (e[0]?.isIntersecting && results.hasNextPage && !results.isFetchingNextPage) results.fetchNextPage(); }, { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, [results]);

  const retry = async () => {
    await api.post(`/api/v1/searches/${id}/retry`);
    setActiveSearch(id);
    qc.invalidateQueries({ queryKey: ["search", id] });
  };

  if (search.isError) return <ErrorView error={search.error} retry={() => search.refetch()} />;
  if (!s) return <div className="grid h-[60vh] place-items-center"><Spinner size={24} /></div>;
  const activeFilters = Object.entries(f).filter(([k, v]) => k !== "sort" && (Array.isArray(v) ? v.length : v)).length;

  return (
    <div className="mx-auto max-w-xl pb-6">
      <section className="px-4 pt-4">
        <div className="flex gap-4">
          <div className="relative h-32 w-[104px] shrink-0 overflow-hidden rounded-3xl bg-surface-2 ring-1 ring-line">
            {s.image_url && <img src={s.image_url} alt="Ваше фото" className="h-full w-full object-cover" />}
            {live && <motion.div className="absolute inset-x-0 h-12 bg-gradient-to-b from-transparent via-white/25 to-transparent"
              animate={{ y: ["-50%", "260%"] }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }} />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[11px] tracking-[0.12em] text-ink-3 uppercase">{MODE_LABEL[s.mode]?.title} · {live ? "в процессе" : s.status === "completed" ? "готово" : "ошибка"}</p>
            {live ? <div className="mt-3"><Stages s={s} /></div> : <AnalysisSummary s={s} />}
          </div>
        </div>
        {live && <AnalysisSummary s={s} />}
        <div className="mt-4"><ProviderChips s={s} names={names} /></div>
        {s.status === "completed" && !s.has_similarity && (
          <p className="mt-3 rounded-2xl bg-surface-2 px-4 py-3 text-xs text-ink-2">Визуальная модель была недоступна, поэтому процент сходства не показан. Результаты отсортированы по релевантности площадок.</p>
        )}
        {s.mode === "cheaper" && s.reference_price && (
          <p className="mt-3 text-xs text-ink-2">Ориентир цены: <span className="font-mono">{s.reference_price} {s.reference_currency}</span></p>
        )}
      </section>

      {s.status === "failed" && (
        <div className="mx-4 mt-6 rounded-3xl bg-surface p-5 ring-1 ring-line">
          <p className="text-[15px] font-semibold">Поиск не завершён</p>
          <p className="mt-1 text-sm text-ink-2">{ERROR_LABEL[(s.error ?? "").split(":")[0]] ?? s.error}</p>
          {(s.error ?? "").startsWith("not_a_product") ? (
            <Link to="/"><Button variant="secondary" className="mt-4 w-full">Загрузить другое фото</Button></Link>
          ) : (
            <Button variant="secondary" className="mt-4 w-full" onClick={retry}><IconRefresh size={18} /> Повторить поиск</Button>
          )}
        </div>
      )}

      {(s.results_count > 0 || live) && (
        <div className="sticky top-0 z-20 mt-5 flex items-center gap-2 bg-bg/90 px-4 py-2.5 backdrop-blur-xl">
          <p className="flex-1 text-sm text-ink-2">
            <span className="font-mono text-ink">{first?.total ?? s.results_count}</span> {live ? "уже найдено" : "предложений"}
          </p>
          <button onClick={() => setSheet(true)} className="relative flex h-9 items-center gap-1.5 rounded-full bg-surface-2 px-3 text-[13px]">
            <IconFilter size={17} /> Фильтры
            {activeFilters > 0 && <span className="grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 font-mono text-[10px] text-white">{activeFilters}</span>}
          </button>
          <button onClick={() => { haptic.select(); setView(view === "grid" ? "list" : "grid"); }} className="grid h-9 w-9 place-items-center rounded-full bg-surface-2" aria-label="Вид">
            {view === "grid" ? <IconList size={18} /> : <IconGrid size={18} />}
          </button>
        </div>
      )}

      <section className="px-4">
        {items.some((p) => p.via) && (
          <p className="mb-3 text-[12px] leading-snug text-ink-3">
            Часть предложений найдена поиском Google по фото и веб-поиском: цену и наличие проверяйте на сайте площадки.
          </p>
        )}
        {items.length > 0 ? (
          <div className={view === "grid" ? "grid grid-cols-2 gap-3" : "space-y-3"}>
            <AnimatePresence initial={false}>
              {items.map((p) => (
                <ProductCard key={p.product_id} p={p} view={view} onFavorite={(on) => fav.mutate({ productId: p.product_id, searchId: id, on })} />
              ))}
            </AnimatePresence>
          </div>
        ) : live || results.isLoading ? (
          <div className={view === "grid" ? "grid grid-cols-2 gap-3" : "space-y-3"}>
            {Array.from({ length: 6 }).map((_, i) => <ProductSkeleton key={i} view={view} />)}
          </div>
        ) : s.status === "completed" ? (
          activeFilters ? (
            <Empty icon={<IconFilter size={26} />} title="Ничего не подходит под фильтры" text="Попробуйте ослабить условия."
              action={<Button variant="secondary" onClick={() => setFilters(id, { ...EMPTY_FILTERS })}><IconClose size={16} /> Сбросить фильтры</Button>} />
          ) : (
            <Empty icon={<IconSearch size={26} />} title="Похожих предложений не нашлось"
              text="Подключённые площадки не вернули подходящих товаров. Попробуйте другой ракурс или режим «Стиль»."
              action={<Link to="/"><Button variant="secondary">Новый поиск</Button></Link>} />
          )
        ) : null}
        <div ref={sentinel} />
        {results.isFetchingNextPage && <div className="grid place-items-center py-6"><Spinner /></div>}
      </section>

      <FiltersSheet open={sheet} onClose={() => setSheet(false)} value={f} onApply={(v) => setFilters(id, v)}
        facets={first?.facets} locked={!me?.plan.features.advanced_filters} names={names} categories={cfg?.categories ?? []} />
    </div>
  );
}
