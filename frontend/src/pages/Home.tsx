import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CropSheet } from "../components/CropSheet";
import { IconArrow, IconCamera, IconClipboard, IconGift, IconHeart, IconImage, IconRefresh, IconSpark } from "../components/icons";
import { Logo } from "../components/Logo";
import { Badge, Button, Card, cx, Segmented, Skeleton } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { MODE_LABEL, plural, relative, timeLeft } from "../lib/format";
import { useConfig, useMe } from "../lib/queries";
import { useUi } from "../lib/store";
import { haptic } from "../lib/telegram";
import type { HistoryItem, Mode, Search } from "../lib/types";

const ACCEPT = "image/jpeg,image/png,image/webp";

function greeting(): string {
  const h = new Date().getHours();
  return h < 5 ? "Доброй ночи" : h < 12 ? "Доброе утро" : h < 18 ? "Добрый день" : "Добрый вечер";
}

export default function Home() {
  const { data: me } = useMe();
  const { data: cfg } = useConfig();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { activeSearchId, setActiveSearch } = useUi();
  const galleryRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<Blob | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [rawSrc, setRawSrc] = useState<string | null>(null);
  const [cropOpen, setCropOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("similar");
  const [refPrice, setRefPrice] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const canPaste = typeof navigator !== "undefined" && !!navigator.clipboard && "read" in navigator.clipboard;

  useEffect(() => { if (me?.preferences.default_mode) setMode(me.preferences.default_mode); }, [me?.preferences.default_mode]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const recent = useQuery({ queryKey: ["history", "recent"], queryFn: () => api.get<{ items: HistoryItem[] }>("/api/v1/history?limit=6") });
  const active = useQuery({
    queryKey: ["search", activeSearchId], enabled: !!activeSearchId,
    queryFn: () => api.get<Search>(`/api/v1/searches/${activeSearchId}`),
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.status) ? 2000 : false),
  });

  const accept = (blob: Blob) => {
    setErr(null);
    const max = cfg?.upload.max_bytes ?? 10 * 1024 * 1024;
    if (!["image/jpeg", "image/png", "image/webp"].includes(blob.type)) { setErr("Поддерживаются JPG, PNG и WEBP."); haptic.error(); return; }
    if (blob.size > max) { setErr(`Файл больше ${Math.round(max / 1048576)} МБ.`); haptic.error(); return; }
    const url = URL.createObjectURL(blob);
    setFile(blob);
    setPreview(url);
    setRawSrc(url);
    haptic.success();
  };

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) => i.type.startsWith("image/"));
      const f = item?.getAsFile();
      if (f) accept(f);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  });

  const pasteFromClipboard = async () => {
    try {
      const items = await navigator.clipboard.read();
      for (const it of items) {
        const t = it.types.find((x) => x.startsWith("image/"));
        if (t) { accept(await it.getType(t)); return; }
      }
      setErr("В буфере обмена нет изображения.");
    } catch {
      setErr("Нет доступа к буферу обмена на этом устройстве.");
    }
  };

  const allowed = me?.plan.features.modes ?? ["similar"];
  const submit = async () => {
    if (!file) return;
    if (!allowed.includes(mode)) { nav("/subscription"); return; }
    setBusy(true);
    setErr(null);
    const fd = new FormData();
    fd.append("image", file, "photo.jpg");
    fd.append("mode", mode);
    if (mode === "cheaper" && refPrice) fd.append("reference_price", refPrice);
    try {
      const s = await api.post<Search>("/api/v1/searches", fd, { "Idempotency-Key": crypto.randomUUID() });
      setActiveSearch(s.id);
      qc.invalidateQueries({ queryKey: ["me"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      haptic.success();
      nav(`/search/${s.id}`);
    } catch (e) {
      haptic.error();
      if (e instanceof ApiError && e.code === "quota_exceeded") setErr("Лимит поисков исчерпан. Оформите PRO или дождитесь обновления лимита.");
      else setErr(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setFile(null); setPreview(null); setRawSrc(null); setErr(null); };
  const brand = cfg?.brand.name ?? "SIFT";
  const running = active.data && ["queued", "running"].includes(active.data.status) ? active.data : null;

  return (
    <div className="mx-auto max-w-xl px-4 pb-6">
      <header className="flex items-center justify-between px-1 pt-4 pb-6">
        <Logo name={brand} />
        {me ? (
          <Link to="/subscription"><Badge tone={me.plan.code === "free" ? "neutral" : "accent"}>{me.plan.title}{me.trial.active ? " · trial" : ""}</Badge></Link>
        ) : <Skeleton className="h-6 w-16 rounded-full" />}
      </header>

      <section className="px-1">
        <p className="text-sm text-ink-2">{greeting()}{me ? `, ${me.first_name}` : ""}</p>
        <h1 className="mt-1 font-display text-[34px] leading-[1.05] font-bold tracking-[-0.03em]">
          Найди<br />эту вещь<span className="text-accent">.</span>
        </h1>
        <p className="mt-3 max-w-sm text-[15px] leading-relaxed text-ink-2">
          Загрузи фотографию, и мы найдём похожие предложения на популярных маркетплейсах.
        </p>
        {me && (
          <div className="mt-4 flex items-center gap-2 text-[13px] text-ink-2">
            <span className="font-mono text-ink">{me.quota.remaining}</span>
            {plural(me.quota.remaining, "поиск", "поиска", "поисков")} {me.quota.window === "day" ? "сегодня" : "в этом месяце"}
            {me.quota.bonus > 0 && <span className="text-ink-3">· включая {me.quota.bonus} бонусных</span>}
          </div>
        )}
      </section>

      <AnimatePresence>
        {running && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            <Card className="mt-5 flex items-center gap-3 p-3" onClick={() => nav(`/search/${running.id}`)}>
              {running.image_url && <img src={running.image_url} className="h-12 w-12 rounded-xl object-cover" alt="" />}
              <div className="flex-1">
                <p className="text-sm font-medium">Поиск выполняется</p>
                <p className="text-xs text-ink-2">Найдено: {running.results_count}. Нажмите, чтобы продолжить</p>
              </div>
              <IconArrow size={18} className="text-ink-3" />
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <section className="mt-6">
        <input ref={galleryRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) accept(f); e.target.value = ""; }} />
        <input ref={cameraRef} type="file" accept={ACCEPT} capture="environment" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) accept(f); e.target.value = ""; }} />

        <AnimatePresence mode="wait">
          {!preview ? (
            <motion.div key="zone" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.98 }}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) accept(f); }}
              onClick={() => galleryRef.current?.click()}
              className={cx("dashed-zone relative flex cursor-pointer flex-col items-center rounded-[28px] bg-surface px-6 pt-10 pb-6 text-center transition-colors",
                drag && "bg-accent-soft")}>
              <motion.div className="mb-5 grid h-[72px] w-[72px] place-items-center rounded-[22px] bg-ink text-bg"
                animate={{ y: [0, -4, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
                <IconImage size={30} />
              </motion.div>
              <p className="font-display text-lg font-semibold">Загрузить фотографию</p>
              <p className="mt-1 font-mono text-[11px] tracking-[0.12em] text-ink-3">JPG · PNG · WEBP</p>
              <div className="mt-6 grid w-full grid-cols-3 gap-2" onClick={(e) => e.stopPropagation()}>
                <button onClick={() => galleryRef.current?.click()} className="flex h-16 flex-col items-center justify-center gap-1 rounded-2xl bg-surface-2 text-[12px] text-ink-2 active:scale-95"><IconImage size={20} />Галерея</button>
                <button onClick={() => cameraRef.current?.click()} className="flex h-16 flex-col items-center justify-center gap-1 rounded-2xl bg-surface-2 text-[12px] text-ink-2 active:scale-95"><IconCamera size={20} />Камера</button>
                <button onClick={pasteFromClipboard} disabled={!canPaste} className="flex h-16 flex-col items-center justify-center gap-1 rounded-2xl bg-surface-2 text-[12px] text-ink-2 active:scale-95 disabled:opacity-40"><IconClipboard size={20} />Вставить</button>
              </div>
            </motion.div>
          ) : (
            <motion.div key="preview" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
              <div className="relative overflow-hidden rounded-[28px] bg-surface ring-1 ring-line">
                <img src={preview} alt="Предпросмотр" className="max-h-[46vh] w-full object-contain" />
                <div className="absolute top-3 right-3 flex gap-2">
                  <button onClick={() => setCropOpen(true)} className="h-9 rounded-full bg-black/55 px-3.5 text-[13px] font-medium text-white backdrop-blur">Обрезать</button>
                  <button onClick={reset} className="grid h-9 w-9 place-items-center rounded-full bg-black/55 text-white backdrop-blur" aria-label="Заново"><IconRefresh size={17} /></button>
                </div>
              </div>
              <div className="mt-4">
                <Segmented value={mode} onChange={setMode}
                  options={(cfg?.modes ?? ["exact", "similar", "cheaper", "discover"]).map((m) => ({ value: m, label: MODE_LABEL[m].title, locked: !allowed.includes(m) }))} />
                <p className="mt-2 px-1 text-xs text-ink-3">{MODE_LABEL[mode].hint}{!allowed.includes(mode) && " · доступно на старших тарифах"}</p>
              </div>
              {mode === "cheaper" && allowed.includes(mode) && (
                <input inputMode="decimal" placeholder="Цена оригинала (необязательно)" value={refPrice}
                  onChange={(e) => setRefPrice(e.target.value.replace(/[^\d.,]/g, "").replace(",", "."))}
                  className="mt-3 h-12 w-full rounded-2xl bg-surface-2 px-4 font-mono text-[15px] outline-none placeholder:font-sans placeholder:text-ink-3 focus:ring-2 focus:ring-accent/60" />
              )}
              <Button className="mt-4 w-full" loading={busy} onClick={submit}>
                {allowed.includes(mode) ? <>Найти похожие <IconArrow size={18} /></> : "Открыть тарифы"}
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
        {err && <p className="mt-3 px-1 text-sm text-bad">{err}</p>}
      </section>

      {me?.trial.available && (
        <Card className="mt-6 flex items-center gap-4 p-4" onClick={() => nav("/subscription")}>
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-accent text-white"><IconGift size={22} /></span>
          <div className="flex-1">
            <p className="text-[15px] font-semibold">{me.trial.days} дня PRO бесплатно</p>
            <p className="text-xs text-ink-2">Без автосписания. Активируется одной кнопкой</p>
          </div>
          <IconArrow size={18} className="text-ink-3" />
        </Card>
      )}
      {me?.trial.active && me.trial.ends_at && (
        <p className="mt-6 px-1 text-xs text-ink-3">Пробный PRO: осталось {timeLeft(me.trial.ends_at)}</p>
      )}

      <section className="mt-8">
        <div className="mb-3 flex items-end justify-between px-1">
          <h2 className="font-display text-[17px] font-semibold">Последние поиски</h2>
          <Link to="/history" className="text-[13px] text-ink-2">История →</Link>
        </div>
        {recent.isLoading ? (
          <div className="flex gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-36 w-28 shrink-0 rounded-2xl" />)}</div>
        ) : recent.data?.items.length ? (
          <div className="no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4">
            {recent.data.items.map((h) => (
              <Link key={h.id} to={`/search/${h.id}`} className="w-28 shrink-0">
                <div className="aspect-[4/5] overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
                  {h.image_url && <img src={h.image_url} alt="" className="h-full w-full object-cover" loading="lazy" />}
                </div>
                <p className="mt-1.5 line-clamp-1 text-[12px] font-medium">{h.title ?? "Фото"}</p>
                <p className="text-[11px] text-ink-3">{relative(h.created_at)}</p>
              </Link>
            ))}
          </div>
        ) : (
          <p className="rounded-2xl bg-surface-2 px-4 py-5 text-center text-sm text-ink-2">Здесь появятся ваши поиски</p>
        )}
      </section>

      <section className="mt-6 grid grid-cols-2 gap-3">
        <Card className="p-4" onClick={() => nav("/saved")}>
          <IconHeart size={20} className="text-ink-2" />
          <p className="mt-3 text-[15px] font-semibold">Избранное</p>
          <p className="text-xs text-ink-2">{me?.favorites_count ?? 0} {plural(me?.favorites_count ?? 0, "вещь", "вещи", "вещей")}</p>
        </Card>
        <Card className="p-4" onClick={() => nav("/subscription")}>
          <IconSpark size={20} className="text-accent" />
          <p className="mt-3 text-[15px] font-semibold">Подписка</p>
          <p className="text-xs text-ink-2">{me?.plan.code === "free" ? "Больше поисков и режимов" : "Управление тарифом"}</p>
        </Card>
      </section>

      <CropSheet open={cropOpen} src={rawSrc} onClose={() => setCropOpen(false)} onDone={(b) => {
        setFile(b);
        setPreview(URL.createObjectURL(b));
        setCropOpen(false);
      }} />
    </div>
  );
}
