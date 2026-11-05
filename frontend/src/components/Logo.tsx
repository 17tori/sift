import { Wordmark } from "./archive";
import { Sieve } from "./Sieve";

/**
 * Brand lockup. For SIFT the default is the sieve mark + SIFT in Cormorant caps; `blackletter` keeps the
 * gothic wordmark (Latin only — never set Cyrillic in it). Any other brand name from config is set in
 * Manrope with the accent dot.
 */
export function Logo({ name, size = 22, variant = "mark" }: { name: string; size?: number; variant?: "mark" | "blackletter" | "serif" | "sans" }) {
  const sift = name.toUpperCase() === "SIFT";
  if (sift && variant === "mark") {
    return (
      <span className="inline-flex items-end gap-[0.45em] text-ink" style={{ fontSize: size }} aria-label="SIFT">
        <Sieve cols={9} width={size * 0.95} />
        <span className="font-serif leading-[0.8] tracking-[0.16em]" style={{ fontSize: size * 1.05 }}>SIFT</span>
      </span>
    );
  }
  if (sift && variant !== "sans") return <Wordmark variant={variant === "serif" ? "serif" : "blackletter"} size={variant === "blackletter" ? size * 1.3 : size} />;
  return (
    <span className="inline-flex items-center font-display font-extrabold tracking-[-0.03em]" style={{ fontSize: size, lineHeight: 1 }}>
      {name}
      <span className="ml-[0.06em] inline-block rounded-full bg-accent" style={{ width: size * 0.2, height: size * 0.2 }} />
    </span>
  );
}
