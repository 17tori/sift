import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Arch, ArchImage, CountUp, LedgerRow, SectionMark } from "../components/archive";
import { IconCheck, IconClose, IconFilter, IconGrid, IconInfo, IconList, IconLock, IconRefresh, IconSearch } from "../components/icons";
import { ProductCard, ProductSkeleton } from "../components/ProductCard";
import { PriceSummary } from "../components/PriceRange";
import { WatchButton } from "../components/WatchButton";
import { Button, Chip, cx, Empty, ErrorView, Field, inputClass, Segmented, Sheet, Spinner } from "../components/ui";
import { api, qs } from "../lib/api";
import { CATEGORY_LABEL, CONDITION_LABEL, ERROR_LABEL, MODE_LABEL, plural } from "../lib/format";
import { dur, ease, shake, spring } from "../lib/motion";
import { useConfig, useMe, useToggleFavorite } from "../lib/queries";
import { EMPTY_FILTERS, type ResultFilters, useUi } from "../lib/store";
import { haptic } from "../lib/telegram";
import type { Results, Search } from "../lib/types";

const STAGES: { key: Search["stage"]; label: string }[] = [
  { key: "uploaded", label: "Фото загружено" },
  { key: "analyzing", label: "Анализируем вещь" },
  { key: "searching", label: "Ищем на площадках" },
  { key: "ranking", label: "Сравниваем" },
];
const ORDER = ["uploaded", "analyzing", "embedding", "searching", "ranking", "done"];

const PROVIDER_STATE: Record<string, string> = {
  searching: "ищет…", done: "", error: "ошибка", timeout: "не ответил", unavailable: "нет доступа", skipped: "пропущен",
};

function Stages({ s }: { s: Search }) {
  const cur = ORDER.indexOf(s.stage === "embedding" ? "analyzing" : s.stage);
  return (
    <ol className="flex flex-col">
      {STAGES.map((st) => {
        const i = ORDER.indexOf(st.key);
        const done = s.status !== "failed" && (cur > i || s.status === "completed");
        const now = !done && cur === i && s.status !== "failed";
        return (
          <li key={st.key} className="flex h-9 items-center gap-3">
            <span className={cx("grid h-[18px] w-[18px] place-items-center rounded-full transition-colors",
              done ? "bg-ink text-bg" : now ? "shadow-[inset_0_0_0_1.5px_var(--accent)]" : "shadow-[inset_0_0_0_1px_var(--line-strong)]")}>
              {done && <IconCheck size={11} strokeWidth={3} />}
              {now && <motion.span className="h-1.5 w-1.5 rounded-full bg-accent" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity }} />}
            </span>
            <span className={cx("text-[15px]", done || now ? "text-ink" : "text-ink-3", now && "font-semibold")}>{st.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** IV. Marketplace stamps: pulse while searching, land like a seal on answer. */
function ProviderStamps({ s, names }: { s: Search; names: Record<string, string> }) {
  const entries = Object.entries(s.providers);
  if (!entries.length) return null;
  const total = entries.reduce((n, [, st]) => n + (st.state === "done" ? st.count ?? 0 : 0), 0);
  return (
    <div className="mt-6">
      <SectionMark numeral="II" label="Площадки" right={<span className="caption text-ink">Найдено <CountUp value={total} className="font-semibold" /></span>} />
      <div className="mt-3 grid grid-cols-4 gap-1.5">
        {entries.map(([code, st]) => {
          const ok = st.state === "done";
          const busy = st.state === "searching";
          return (
            <motion.div key={code + st.state}
              initial={ok ? { scale: 1.15, rotate: -2, opacity: 0 } : false}
              animate={busy ? { opacity: [0.45, 1, 0.45] } : { scale: 1, rotate: 0, opacity: 1 }}
              transition={busy ? { duration: 1.2, repeat: Infinity, ease: ease.inOut } : spring.bouncy}
              onAnimationComplete={() => { if (ok) haptic.tap(); }}
              className={cx("flex flex-col gap-1 border p-2.5", ok ? "border-relic" : busy ? "border-line-strong" : "border-line")}>
              <span className={cx("truncate font-mono text-[10px] tracking-[0.1em] uppercase", ok ? "text-relic-ink" : "text-ink-3")}>{names[code] ?? code}</span>
              <span className={cx("font-mono text-[11px]", st.state === "error" || st.state === "timeout" ? "text-bad" : ok ? "text-ink" : "text-ink-3")}>
                {ok ? `найдено ${st.count ?? 0}` : PROVIDER_STATE[st.state]}
              </span>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

function AnalysisLedger({ s }: { s: Search }) {
  const a = s.analysis;
  if (!a || a.vision_error) return null;
  const rows = [
    a.category && { k: "Категория", v: [CATEGORY_LABEL[a.category], a.subcategory].filter(Boolean).join(" · ") },
    a.material && { k: "Материал", v: a.material },
    a.silhouette && { k: "Силуэт", v: a.silhouette },
    a.pattern && { k: "Узор", v: a.pattern },
    a.brand?.name && a.brand.confidence !== "none" && { k: "Бренд", v: `${a.brand.name} · ${a.brand.confidence === "high" ? "уверенно" : "предп."}` },
  ].filter(Boolean) as { k: string; v: string }[];
  return (
    <div className="mt-6">
      <SectionMark numeral="I" label="Описание экспоната" />
      <div className="mt-1.5">
        {rows.map((r, i) => <LedgerRow key={r.k} k={r.k} v={r.v} index={i} typewriter={i < 3} />)}
        {!!a.colors?.length && (
          <LedgerRow k="Цвета" index={rows.length}>
            <span className="flex gap-1.5">
              {a.colors.map((c, i) => (
                <motion.span key={c.hex + c.name} title={c.name} className="h-[18px] w-[18px] rounded-full shadow-[inset_0_0_0_1px_var(--line-strong)]"
                  style={{ background: c.hex }} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                  transition={{ ...spring.bouncy, delay: 0.2 + i * 0.06 }} />
              ))}
            </span>
          </LedgerRow>
        )}
      </div>
    </div>
  );
}

function ResultTitle({ s }: { s: Search }) {
  const a = s.analysis;
  const title = a && !a.vision_error ? (a.title_ru || a.title_en) : null;
  const words = (title ?? "Результаты поиска").split(" ");
  const last = words.pop();
  const tags = a && !a.vision_error ? [a.material, a.silhouette, ...(a.style ?? []).slice(0, 2)].filter(Boolean) as string[] : [];
  return (
    <>
      <h1 className="font-serif text-[36px] leading-[36px] font-light tracking-[-0.015em]">{words.join(" ")} <i className="font-normal">{last}</i></h1>
      {(tags.length > 0 || !!a?.colors?.length) && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {tags.map((tg) => <span key={tg} className="inline-flex h-7 items-center rounded-full px-2.5 text-[12px] text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)]">{tg}</span>)}
          {(a?.colors ?? []).slice(0, 2).map((c) => (
            <span key={c.hex} className="inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[12px] text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)]">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.hex }} />{c.name}
            </span>
          ))}
        </div>
      )}
    </>
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
  const nav = useNavigate();
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
      <section className="px-5 pt-1">
        {live ? (
          <>
            <div className="flex justify-center">
              <motion.div layoutId="query-photo" transition={spring.soft}>
                <Arch morph className="h-[264px] w-[200px]">
                  {s.image_url && <img src={s.image_url} alt="Ваше фото" className="h-full w-full object-cover" />}
                  {(s.stage === "analyzing" || s.stage === "embedding" || s.stage === "uploaded") && (
                    <motion.div className="absolute inset-x-0 h-px bg-accent shadow-[0_0_12px_2px_rgba(82,107,255,.7)]"
                      animate={{ top: ["8%", "92%"] }} transition={{ duration: dur.scan, repeat: Infinity, repeatType: "reverse", ease: ease.inOut }} />
                  )}
                </Arch>
              </motion.div>
            </div>
            <p className="caption mt-3 text-center text-ink-3">№ {s.id.slice(0, 4).toUpperCase()} · Запрос · {new Date(s.created_at).toLocaleDateString("ru-RU")}</p>
            <div className="mt-5"><Stages s={s} /></div>
            <AnalysisLedger s={s} />
          </>
        ) : (
          <div className="flex items-end gap-4">
            <motion.div layoutId="query-photo" transition={spring.soft}>
              <ArchImage src={s.image_url} alt="Ваше фото" className="h-[122px] w-[92px] shrink-0" />
            </motion.div>
            <div className="min-w-0 flex-1 pb-0.5">
              <p className="caption text-ink-3">№ {s.id.slice(0, 4).toUpperCase()} · {MODE_LABEL[s.mode]?.title} · {s.status === "completed" ? new Date(s.created_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) : "ошибка"}</p>
            </div>
          </div>
        )}
        {!live && <div className="mt-3"><ResultTitle s={s} /></div>}
        {s.status === "completed" && s.results_count > 0 && (
          <motion.div className="mt-5" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <WatchButton searchId={id} />
          </motion.div>
        )}
        <ProviderStamps s={s} names={names} />
        {s.status === "completed" && first?.price_range && (
          <PriceSummary range={first.price_range} onOpen={(p) => nav(`/search/${id}/item/${p.product_id}`)} />
        )}
        {s.status === "completed" && !s.has_similarity && (
          <p className="mt-3 text-[12px] leading-[17px] text-ink-2">Визуальная модель была недоступна, поэтому процент сходства не показан. Результаты отсортированы по релевантности площадок.</p>
        )}
        {s.mode === "cheaper" && s.reference_price && (
          <p className="caption mt-3 text-ink-2">Ориентир цены · <span className="text-ink">{s.reference_price} {s.reference_currency}</span></p>
        )}
        {(s.results_count > 0 || live) && <SectionMark numeral="III" label="Результаты" className="mt-6" />}
      </section>

      {s.status === "failed" && (
        <motion.div className="mx-5 mt-6 p-5 shadow-[inset_0_0_0_1px_var(--line-strong)]" animate={shake} onAnimationStart={() => haptic.error()}>
          <p className="font-serif text-[28px] leading-8 font-light">Поиск <i className="font-normal">не завершён</i></p>
          <p className="mt-1 text-sm text-ink-2">{ERROR_LABEL[(s.error ?? "").split(":")[0]] ?? s.error}</p>
          {(s.error ?? "").startsWith("not_a_product") ? (
            <Link to="/"><Button variant="secondary" className="mt-4 w-full">Загрузить другое фото</Button></Link>
          ) : (
            <Button variant="secondary" className="mt-4 w-full" onClick={retry}><IconRefresh size={18} /> Повторить поиск</Button>
          )}
        </motion.div>
      )}

      {(s.results_count > 0 || live) && (
        <div className="sticky top-0 z-20 mt-2.5 flex items-center gap-2 border-b border-line bg-bg px-5 py-2.5">
          <p className="caption flex-1 text-ink">
            <CountUp value={first?.total ?? s.results_count} className="font-semibold" /> {live ? "уже найдено" : plural(first?.total ?? s.results_count, "предложение", "предложения", "предложений")}
          </p>
          <button onClick={() => { haptic.tap(); setSheet(true); }} className="relative flex h-[34px] items-center gap-1.5 rounded-full bg-surface-2 px-3 text-[13px] font-medium">
            <IconFilter size={15} /> Фильтры
            {activeFilters > 0 && <span className="font-mono text-[11px] text-ink-3">{activeFilters}</span>}
          </button>
          <Segmented value={view} onChange={setView} options={[
            { value: "grid", label: <IconGrid size={15} aria-label="Сетка" /> },
            { value: "list", label: <IconList size={15} aria-label="Список" /> },
          ]} />
        </div>
      )}

      <section className="px-5 pt-3">
        {items.some((p) => p.via) && (
          <p className="mb-4 flex gap-2 text-[12px] leading-[17px] text-ink-2">
            <IconInfo size={15} className="mt-px shrink-0" />
            Часть предложений найдена по фото в Google и веб-поиском. Цену и наличие проверяйте на сайте площадки.
          </p>
        )}
        {items.length > 0 ? (
          <LayoutGroup>
            <div className={view === "grid" ? "grid grid-cols-2 gap-x-3 gap-y-6" : "flex flex-col"}>
              <AnimatePresence initial={false}>
                {items.map((p, i) => (
                  <ProductCard key={p.product_id} p={p} view={view} index={i}
                    onOpen={() => nav(`/search/${id}/item/${p.product_id}`)}
                    onFavorite={(on) => fav.mutate({ productId: p.product_id, searchId: id, on })} />
                ))}
              </AnimatePresence>
            </div>
          </LayoutGroup>
        ) : live || results.isLoading ? (
          <div className={view === "grid" ? "grid grid-cols-2 gap-x-3 gap-y-6" : "flex flex-col"}>
            {Array.from({ length: 6 }).map((_, i) => <ProductSkeleton key={i} view={view} />)}
          </div>
        ) : s.status === "completed" ? (
          activeFilters ? (
            <Empty icon={<IconFilter size={26} />} title="Под фильтры *ничего*" text="Попробуйте ослабить условия."
              action={<Button variant="secondary" onClick={() => setFilters(id, { ...EMPTY_FILTERS })}><IconClose size={16} /> Сбросить фильтры</Button>} />
          ) : (
            <Empty icon={<IconSearch size={26} />} title="Похожих *не нашлось*"
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
