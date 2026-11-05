import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CropSheet } from "../components/CropSheet";
import { Arch, ArchImage, SectionMark, Stamp } from "../components/archive";
import { IconArrow, IconCamera, IconClipboard, IconHanger, IconHeart, IconImage, IconLock, IconRefresh, IconStar } from "../components/icons";
import { Logo } from "../components/Logo";
import { Button, Card, cx, Row, Skeleton } from "../components/ui";
import { cardVariants, shake, spring, t } from "../lib/motion";
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
    <div className="mx-auto max-w-xl px-5 pb-6">
      <header className="flex items-center justify-between pt-3">
        <Logo name={brand} size={24} />
        {me ? (
          <Link to="/subscription" className="caption text-ink-2">
            <span className="font-semibold text-ink">{me.quota.remaining}</span> {plural(me.quota.remaining, "поиск", "поиска", "поисков")} {me.quota.window === "day" ? "сегодня" : "в месяце"}
          </Link>
        ) : <Skeleton className="h-3.5 w-28" />}
      </header>
      <div className="mt-3.5 h-px bg-line-strong" />

      <section className="mt-5">
        <p className="text-[15px] text-ink-2">{greeting()}{me ? `, ${me.first_name}` : ""}</p>
        <h1 className="mt-1 font-serif text-[56px] leading-[52px] font-light tracking-[-0.02em]">Найди эту <i className="font-normal">вещь</i>.</h1>
        {me && me.quota.bonus > 0 && <p className="caption mt-3 text-ink-3">Включая {me.quota.bonus} бонусных</p>}
      </section>

      <AnimatePresence>
        {running && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={t.element}>
            <Card className="mt-5 flex items-center gap-3 p-3" onClick={() => nav(`/search/${running.id}`)}>
              {running.image_url && <ArchImage src={running.image_url} alt="" className="h-14 w-11 shrink-0" />}
              <div className="flex-1">
                <p className="text-sm font-medium">Поиск выполняется</p>
                <p className="caption mt-0.5 text-ink-3">Найдено {running.results_count}</p>
              </div>
              <IconArrow size={18} className="text-ink-3" />
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <section className="mt-7">
        <input ref={galleryRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) accept(f); e.target.value = ""; }} />
        <input ref={cameraRef} type="file" accept={ACCEPT} capture="environment" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) accept(f); e.target.value = ""; }} />

        <AnimatePresence mode="wait">
          {!preview ? (
            <motion.div key="zone" initial={{ opacity: 0 }} animate={err ? { opacity: 1, ...shake } : { opacity: 1 }} exit={{ opacity: 0 }} transition={t.element}>
              <Arch dashed outlineClass={drag ? "text-accent" : err ? "text-bad" : "text-line-strong"} className="mx-auto aspect-[35/32] w-full">
                <button type="button" aria-label="Загрузить фотографию"
                  onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                  onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) accept(f); }}
                  onClick={() => galleryRef.current?.click()}
                  className={cx("flex h-full w-full flex-col items-center justify-end pb-9 text-center transition-colors", drag && "bg-accent-soft")}>
                  <IconHanger size={52} strokeWidth={1.1} className="text-ink-2" />
                  <span className="mt-4 text-[15px] leading-[22px]">Фото вещи, скриншот<br />или кадр из ленты</span>
                  <span className="caption mt-2.5 text-ink-3">JPG · PNG · WEBP</span>
                </button>
              </Arch>
              <div className="mt-4 grid grid-cols-3 gap-2">
                <Button onClick={() => galleryRef.current?.click()} className="px-2"><IconImage size={18} />Галерея</Button>
                <Button variant="secondary" onClick={() => cameraRef.current?.click()} className="px-2"><IconCamera size={18} />Камера</Button>
                <Button variant="secondary" onClick={pasteFromClipboard} disabled={!canPaste} className="px-2"><IconClipboard size={18} />Вставить</Button>
              </div>
            </motion.div>
          ) : (
            <motion.div key="preview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={t.element}>
              <motion.div layoutId="query-photo" transition={spring.soft} className="relative overflow-hidden rounded-[4px] bg-surface-2 shadow-[inset_0_0_0_1px_var(--line)]">
                <img src={preview} alt="Предпросмотр" className="max-h-[46vh] w-full object-contain" />
                <div className="absolute top-3 right-3 flex gap-2">
                  <button onClick={() => setCropOpen(true)} className="h-9 rounded-full bg-black/55 px-3.5 text-[13px] font-medium text-white backdrop-blur">Обрезать</button>
                  <button onClick={reset} className="grid h-9 w-9 place-items-center rounded-full bg-black/55 text-white backdrop-blur" aria-label="Заново"><IconRefresh size={17} /></button>
                </div>
              </motion.div>
              <SectionMark numeral="II" label="Режим поиска" className="mt-6" />
              <div className="mt-3 grid grid-cols-2 gap-2">
                {(cfg?.modes ?? ["similar", "exact", "cheaper", "discover"]).map((m) => {
                  const locked = !allowed.includes(m);
                  return (
                    <motion.button key={m} type="button" whileTap={{ scale: 0.97 }} transition={spring.bouncy}
                      onClick={() => { haptic.select(); setMode(m); }}
                      className={cx("flex flex-col items-start gap-1 rounded-xl p-3 text-left", locked && "opacity-70",
                        mode === m ? "shadow-[inset_0_0_0_1.5px_var(--ink)]" : "shadow-[inset_0_0_0_1px_var(--line-strong)]")}>
                      <span className="flex items-center gap-1.5 text-[14px] font-semibold">{locked && <IconLock size={13} />}{MODE_LABEL[m].title}</span>
                      <span className="text-[12px] leading-4 text-ink-2">{MODE_LABEL[m].hint}</span>
                    </motion.button>
                  );
                })}
              </div>
              {mode === "cheaper" && allowed.includes(mode) && (
                <input inputMode="decimal" placeholder="Цена оригинала (необязательно)" value={refPrice}
                  onChange={(e) => setRefPrice(e.target.value.replace(/[^\d.,]/g, "").replace(",", "."))}
                  className="mt-3 h-12 w-full rounded-xl bg-surface-2 px-4 font-mono text-[15px] outline-none placeholder:font-sans placeholder:text-ink-3 focus:ring-2 focus:ring-accent/60" />
              )}
              <Button className="mt-4 w-full" loading={busy} onClick={submit}>
                {allowed.includes(mode) ? <>Найти <IconArrow size={18} /></> : "Открыть тарифы"}
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
        {err && <p className="mt-3 text-sm text-bad">{err}</p>}
      </section>

      {me?.trial.available && (
        <Card vellum className="mt-6 flex items-center gap-4 p-[18px]" onClick={() => nav("/subscription")}>
          <span className="font-serif text-[44px] leading-10 italic">{me.trial.days}</span>
          <div className="flex-1">
            <p className="font-display text-[16px] font-bold tracking-[-0.015em]">{plural(me.trial.days, "день", "дня", "дней")} PRO бесплатно</p>
            <p className="text-[13px] text-ink-2">Без автосписания. Все режимы и площадки.</p>
          </div>
          <Stamp>PRO</Stamp>
        </Card>
      )}
      {me?.trial.active && me.trial.ends_at && (
        <p className="caption mt-6 text-ink-3">Пробный PRO · осталось {timeLeft(me.trial.ends_at)}</p>
      )}

      <section className="mt-8">
        <SectionMark numeral="I" label="Последние поиски" right={<Link to="/history" className="text-[13px] text-ink-2">Все</Link>} />
        {recent.isLoading ? (
          <div className="mt-4 flex gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[124px] w-24 shrink-0" />)}</div>
        ) : recent.data?.items.length ? (
          <div className="no-scrollbar -mx-5 mt-4 flex gap-3 overflow-x-auto px-5">
            {recent.data.items.map((h, i) => (
              <motion.div key={h.id} custom={i} variants={cardVariants} initial="hidden" animate="show">
                <Link to={`/search/${h.id}`} className="block w-24 shrink-0">
                  <ArchImage src={h.image_url} alt="" className="h-[124px] w-24" />
                  <p className="mt-2 line-clamp-1 text-[13px]">{h.title ?? "Фото"}</p>
                  <p className="inv mt-0.5">{relative(h.created_at)} · {h.results_count}</p>
                </Link>
              </motion.div>
            ))}
          </div>
        ) : (
          <p className="mt-4 py-5 text-center text-sm text-ink-2">Здесь появятся ваши поиски</p>
        )}
      </section>

      <section className="mt-7 border-t border-line">
        <Row icon={<IconHeart size={20} />} title="Моя коллекция" value={me?.favorites_count ?? 0} onClick={() => nav("/saved")} />
        <Row icon={<IconStar size={20} />} title="Подписка" value={me?.plan.title ?? ""} onClick={() => nav("/subscription")} />
      </section>

      <CropSheet open={cropOpen} src={rawSrc} onClose={() => setCropOpen(false)} onDone={(b) => {
        setFile(b);
        setPreview(URL.createObjectURL(b));
        setCropOpen(false);
      }} />
    </div>
  );
}
