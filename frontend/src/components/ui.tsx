import { AnimatePresence, motion } from "motion/react";
import { type ButtonHTMLAttributes, type ReactNode, useEffect } from "react";
import { haptic } from "../lib/telegram";
import { IconClose, IconLock } from "./icons";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
export function Button({ variant = "primary", loading, className, children, onClick, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: "bg-accent text-accent-ink hover:brightness-110",
    secondary: "bg-surface-2 text-ink hover:bg-line-strong",
    ghost: "bg-transparent text-ink-2 hover:text-ink",
    danger: "bg-transparent text-bad ring-1 ring-inset ring-bad/30",
  };
  return (
    <button
      {...p}
      onClick={(e) => { haptic.tap(); onClick?.(e); }}
      disabled={p.disabled || loading}
      className={cx("relative inline-flex h-12 items-center justify-center gap-2 rounded-2xl px-5 text-[15px] font-semibold",
        "transition-[transform,filter,background] active:scale-[0.98] disabled:opacity-50", styles[variant], className)}
    >
      {loading && <span className="absolute inset-0 grid place-items-center"><Spinner /></span>}
      <span className={cx("inline-flex items-center gap-2", loading && "opacity-0")}>{children}</span>
    </button>
  );
}

export function Spinner({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="animate-spin" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" fill="none" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function Card({ className, children, onClick }: { className?: string; children: ReactNode; onClick?: () => void }) {
  return (
    <div onClick={onClick} className={cx("rounded-[var(--radius-card)] bg-surface shadow-[var(--shadow)] ring-1 ring-line",
      onClick && "cursor-pointer active:scale-[0.99] transition-transform", className)}>
      {children}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("shimmer rounded-xl", className)} />;
}

export function Chip({ active, children, onClick, locked }: { active?: boolean; children: ReactNode; onClick?: () => void; locked?: boolean }) {
  return (
    <button onClick={() => { haptic.select(); onClick?.(); }}
      className={cx("inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium transition-colors",
        active ? "bg-ink text-bg" : "bg-surface-2 text-ink-2 hover:text-ink", locked && "opacity-60")}>
      {locked && <IconLock size={14} />}
      {children}
    </button>
  );
}

export function Segmented<T extends string>({ value, options, onChange }: {
  value: T; options: { value: T; label: ReactNode; locked?: boolean }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="relative flex rounded-2xl bg-surface-2 p-1">
      {options.map((o) => (
        <button key={o.value} onClick={() => { haptic.select(); onChange(o.value); }}
          className={cx("relative z-10 flex h-9 flex-1 items-center justify-center gap-1 rounded-xl text-[13px] font-medium transition-colors",
            value === o.value ? "text-ink" : "text-ink-3")}>
          {value === o.value && (
            <motion.span layoutId={`seg-${options.map((x) => x.value).join("")}`} className="absolute inset-0 -z-10 rounded-xl bg-surface shadow-sm ring-1 ring-line"
              transition={{ type: "spring", bounce: 0.15, duration: 0.35 }} />
          )}
          {o.locked && <IconLock size={12} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button role="switch" aria-checked={checked} disabled={disabled} onClick={() => { haptic.select(); onChange(!checked); }}
      className={cx("relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-40", checked ? "bg-accent" : "bg-line-strong")}>
      <motion.span className="absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow" animate={{ x: checked ? 20 : 0 }}
        transition={{ type: "spring", bounce: 0.2, duration: 0.3 }} />
    </button>
  );
}

export function Empty({ icon, title, text, action }: { icon: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-8 py-16 text-center">
      <div className="mb-5 grid h-16 w-16 place-items-center rounded-3xl bg-surface-2 text-ink-2">{icon}</div>
      <h3 className="font-display text-lg font-semibold tracking-tight">{title}</h3>
      {text && <p className="mt-1.5 max-w-xs text-sm leading-relaxed text-ink-2">{text}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorView({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Не удалось загрузить данные.";
  return (
    <div className="flex flex-col items-center px-8 py-14 text-center">
      <p className="text-sm text-ink-2">{msg}</p>
      {retry && <Button variant="secondary" className="mt-4 h-10" onClick={retry}>Повторить</Button>}
    </div>
  );
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div role="dialog" className="safe-bottom fixed inset-x-0 bottom-0 z-50 max-h-[88vh] overflow-y-auto rounded-t-[28px] bg-bg ring-1 ring-line"
            initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", bounce: 0, duration: 0.38 }}
            drag="y" dragConstraints={{ top: 0, bottom: 0 }} dragElastic={{ top: 0, bottom: 0.6 }}
            onDragEnd={(_, i) => { if (i.offset.y > 120 || i.velocity.y > 600) onClose(); }}>
            <div className="sticky top-0 z-10 bg-bg/95 px-5 pt-3 pb-2 backdrop-blur">
              <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-strong" />
              <div className="flex items-center justify-between">
                <h3 className="font-display text-lg font-semibold">{title}</h3>
                <button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-full bg-surface-2 text-ink-2" aria-label="Закрыть">
                  <IconClose size={18} />
                </button>
              </div>
            </div>
            <div className="px-5 pb-6">{children}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between px-1">
      <h2 className="font-display text-[17px] font-semibold tracking-tight">{children}</h2>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <header className="flex items-start justify-between px-5 pt-4 pb-5">
      <div>
        <h1 className="font-display text-[28px] leading-tight font-bold tracking-[-0.02em]">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {right}
    </header>
  );
}

export function Row({ icon, title, value, onClick, danger }: { icon?: ReactNode; title: string; value?: ReactNode; onClick?: () => void; danger?: boolean }) {
  return (
    <button onClick={() => { haptic.tap(); onClick?.(); }} className="flex w-full items-center gap-3 px-4 py-3.5 text-left active:bg-surface-2">
      {icon && <span className={cx("grid h-9 w-9 place-items-center rounded-xl bg-surface-2", danger ? "text-bad" : "text-ink-2")}>{icon}</span>}
      <span className={cx("flex-1 text-[15px]", danger && "text-bad")}>{title}</span>
      {value !== undefined && <span className="text-sm text-ink-2">{value}</span>}
    </button>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "good" | "bad" }) {
  const t = { neutral: "bg-surface-2 text-ink-2", accent: "bg-accent-soft text-accent", good: "bg-good/12 text-good", bad: "bg-bad/12 text-bad" }[tone];
  return <span className={cx("inline-flex h-6 items-center rounded-full px-2.5 text-[11px] font-semibold tracking-wide uppercase", t)}>{children}</span>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</span>
      {children}
    </label>
  );
}

export const inputClass = "h-12 w-full rounded-2xl bg-surface-2 px-4 text-[15px] outline-none ring-accent/60 placeholder:text-ink-3 focus:ring-2";
