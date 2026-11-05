import { AnimatePresence, animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { type ButtonHTMLAttributes, type ReactNode, useEffect } from "react";
import { dur, ease, press, shake, spring, t } from "../lib/motion";
import { haptic } from "../lib/telegram";
import { Sieve } from "./Sieve";
import { IconClose, IconLock } from "./icons";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
type MotionConflicts = "onAnimationStart" | "onDrag" | "onDragStart" | "onDragEnd" | "style";
export function Button({ variant = "primary", loading, className, children, onClick, shakeKey, ...p }:
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, MotionConflicts> & { variant?: Variant; loading?: boolean; shakeKey?: number }) {
  const styles: Record<Variant, string> = {
    primary: "bg-accent text-accent-ink",
    secondary: "bg-transparent text-ink shadow-[inset_0_0_0_1px_var(--line-strong)]",
    ghost: "bg-transparent text-ink-2",
    danger: "bg-transparent text-bad shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--bad)_40%,transparent)]",
  };
  return (
    <motion.button
      {...p}
      key={shakeKey}
      animate={shakeKey ? shake : undefined}
      whileTap={{ scale: press.button }}
      transition={spring.bouncy}
      onClick={(e) => { haptic.tap(); onClick?.(e); }}
      disabled={p.disabled || loading}
      className={cx("relative inline-flex h-[52px] items-center justify-center gap-2 rounded-[14px] px-5 font-display text-[15px] font-bold tracking-[-0.01em]",
        "disabled:opacity-45", styles[variant], className)}
    >
      {loading && <span className="absolute inset-0 grid place-items-center"><Spinner /></span>}
      <span className={cx("inline-flex items-center gap-2", loading && "opacity-0")}>{children}</span>
    </motion.button>
  );
}

export function Spinner({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="animate-spin" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2" fill="none" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/** Surface card. Depth comes from the surface + hairline, not shadow. `vellum` = archival record card. */
export function Card({ className, children, onClick, vellum }: { className?: string; children: ReactNode; onClick?: () => void; vellum?: boolean }) {
  return (
    <motion.div onClick={onClick} whileTap={onClick ? { scale: press.card } : undefined} transition={spring.bouncy}
      className={cx(vellum ? "rounded-[4px] bg-vellum" : "rounded-[var(--radius-card)] bg-surface", "shadow-[inset_0_0_0_1px_var(--line)]",
        onClick && "cursor-pointer", className)}>
      {children}
    </motion.div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("shimmer rounded-[4px]", className)} />;
}

export function Chip({ active, children, onClick, locked }: { active?: boolean; children: ReactNode; onClick?: () => void; locked?: boolean }) {
  return (
    <motion.button whileTap={{ scale: press.button }} transition={spring.bouncy}
      onClick={() => { haptic.select(); onClick?.(); }}
      className={cx("inline-flex h-[34px] shrink-0 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium transition-colors",
        active ? "bg-ink text-bg" : "bg-surface-2 text-ink-2", locked && "opacity-70")}>
      {locked && <IconLock size={13} />}
      {children}
    </motion.button>
  );
}

export function Segmented<T extends string>({ value, options, onChange }: {
  value: T; options: { value: T; label: ReactNode; locked?: boolean }[]; onChange: (v: T) => void;
}) {
  const group = options.map((x) => x.value).join("");
  return (
    <div className="relative flex rounded-xl bg-surface-2 p-[3px]">
      {options.map((o) => (
        <button key={o.value} onClick={() => { haptic.select(); onChange(o.value); }}
          className={cx("relative z-10 flex h-9 flex-1 items-center justify-center gap-1 rounded-[9px] text-[13px] font-medium transition-colors",
            value === o.value ? "text-ink" : "text-ink-3")}>
          {value === o.value && (
            <motion.span layoutId={`seg-${group}`} className="absolute inset-0 -z-10 rounded-[9px] bg-surface shadow-[0_0_0_1px_var(--line)]"
              transition={spring.soft} />
          )}
          {o.locked && <IconLock size={12} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => { haptic.select(); onChange(!checked); }}
      className={cx("relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-40", checked ? "bg-accent" : "bg-line-strong")}>
      <motion.span className="absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white" animate={{ x: checked ? 20 : 0 }} transition={spring.bouncy} />
    </button>
  );
}

/**
 * Empty state: breathing rosette + Cormorant title. `title` may contain one *word* in asterisks — it is set in italic.
 * `icon` is kept for API compatibility and rendered small under the rosette when given.
 */
export function Empty({ title, text, action }: { /** kept for call sites; the sieve replaces icons */ icon?: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <motion.div className="flex flex-col items-center px-8 py-14 text-center" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={t.element}>
      {/* The sieve without its blue dot: nothing was found. */}
      <div className="text-ink">
        <Sieve cols={11} accent={null} width={84} animate="breathe" />
      </div>
      <h3 className="mt-7 font-serif text-[34px] leading-[38px] font-light">{italicize(title)}</h3>
      {text && <p className="mt-2.5 max-w-[290px] text-[15px] leading-[22px] text-ink-2">{text}</p>}
      {action && <div className="mt-6">{action}</div>}
    </motion.div>
  );
}

/** "Моя *коллекция*" → Моя <i>коллекция</i>. */
export function italicize(s: string): ReactNode {
  const parts = s.split("*");
  return parts.map((p, i) => (i % 2 ? <i key={i} className="font-normal">{p}</i> : <span key={i}>{p}</span>));
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

/** Bottom sheet: soft spring, drag by the handle, backdrop opacity follows position, velocity-aware dismissal. */
export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: string; children: ReactNode }) {
  const y = useMotionValue(0);
  const backdrop = useTransform(y, [0, 400], [1, 0]);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!open) return;
    y.set(0);
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose, y]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="fixed inset-0 z-40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: dur.element }} onClick={onClose}>
            <motion.div className="absolute inset-0 bg-black/50" style={{ opacity: backdrop }} />
          </motion.div>
          <motion.div role="dialog" aria-label={title}
            className="safe-bottom fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[88vh] max-w-xl overflow-y-auto rounded-t-[24px] bg-bg shadow-[inset_0_1px_0_var(--line-strong)]"
            style={{ y }}
            initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={reduce ? t.reduced : spring.soft}
            drag="y" dragConstraints={{ top: 0, bottom: 0 }} dragElastic={{ top: 0, bottom: 0.6 }}
            onDragEnd={(_, i) => {
              if (i.offset.y > 120 || i.velocity.y > 600) onClose();
              else animate(y, 0, { ...spring.soft, velocity: i.velocity.y });
            }}>
            <div className="sticky top-0 z-10 bg-bg px-5 pt-2.5 pb-2">
              <div className="mx-auto mb-3.5 h-1 w-10 rounded-full bg-line-strong" />
              <div className="flex items-center justify-between">
                <h3 className="font-display text-[20px] leading-[26px] font-bold tracking-[-0.02em]">{title}</h3>
                <button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-full bg-surface-2 text-ink-2" aria-label="Закрыть">
                  <IconClose size={16} />
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

/** Swiss section title. With `numeral` it becomes the archival section mark. */
export function SectionTitle({ children, action, numeral }: { children: ReactNode; action?: ReactNode; numeral?: string }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      {numeral && <span className="font-serif text-[22px] leading-none font-light">{numeral}</span>}
      <h2 className="caption text-ink-2">{numeral ? "— " : ""}{children}</h2>
      <span className="h-px flex-1 bg-line-strong" />
      {action}
    </div>
  );
}

/**
 * Editorial page header: mono section label with Roman numeral, Cormorant H1 (one *word* italic), optional subtitle.
 * Without `numeral` it renders the Swiss variant (Manrope H2) — for working screens such as Settings and Admin.
 */
export function PageHeader({ title, subtitle, right, numeral, label, serif = true }: {
  title: string; subtitle?: ReactNode; right?: ReactNode; numeral?: string; label?: string; serif?: boolean;
}) {
  return (
    <header className="px-5 pt-2 pb-5">
      {(numeral || label) && (
        <div className="mb-3.5 flex items-center gap-3">
          {numeral && <span className="font-serif text-[22px] leading-none font-light">{numeral}</span>}
          {label && <span className="caption text-ink-2">{numeral ? "— " : ""}{label}</span>}
          <span className="h-px flex-1 bg-line-strong" />
          {right}
        </div>
      )}
      <div className="flex items-start justify-between gap-4">
        <h1 className={serif
          ? "font-serif text-[48px] leading-[48px] font-light tracking-[-0.02em]"
          : "font-display text-[28px] leading-[32px] font-bold tracking-[-0.025em]"}>
          {italicize(title)}
        </h1>
        {!(numeral || label) && right}
      </div>
      {subtitle && <p className="mt-2 text-[15px] leading-[22px] text-ink-2">{subtitle}</p>}
    </header>
  );
}

export function Row({ icon, title, value, onClick, danger }: { icon?: ReactNode; title: string; value?: ReactNode; onClick?: () => void; danger?: boolean }) {
  return (
    <button onClick={() => { haptic.tap(); onClick?.(); }}
      className="flex min-h-[54px] w-full items-center gap-3.5 border-b border-line text-left transition-colors active:bg-surface-2">
      {icon && <span className={cx("grid h-6 w-6 place-items-center", danger ? "text-bad" : "text-ink-2")}>{icon}</span>}
      <span className={cx("flex-1 text-[15px]", danger && "text-bad")}>{title}</span>
      {value !== undefined && <span className="caption text-ink-3">{value}</span>}
    </button>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "good" | "bad" | "relic" }) {
  const map = {
    neutral: "bg-surface-2 text-ink-2",
    accent: "bg-accent text-white",
    good: "bg-[color-mix(in_srgb,var(--good)_14%,transparent)] text-good",
    bad: "bg-[color-mix(in_srgb,var(--bad)_14%,transparent)] text-bad",
    relic: "bg-transparent text-relic-ink shadow-[inset_0_0_0_1px_var(--relic)]",
  };
  return <span className={cx("inline-flex h-5 items-center rounded-[3px] px-[7px] font-mono text-[10px] tracking-[0.1em] uppercase", map[tone])}>{children}</span>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="caption mb-2 block text-ink-3">{label}</span>
      {children}
    </label>
  );
}

export const inputClass = "h-12 w-full rounded-xl bg-surface-2 px-4 text-[15px] outline-none ring-accent/60 placeholder:text-ink-3 focus:ring-2";

/** Keep easing token import reachable for consumers that style CSS transitions inline. */
export const cssEase = { outExpo: `cubic-bezier(${ease.outExpo.join(",")})`, inOut: `cubic-bezier(${ease.inOut.join(",")})` };
