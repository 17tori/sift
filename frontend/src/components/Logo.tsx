import { Wordmark } from "./archive";

/**
 * Brand wordmark. For the SIFT name: blackletter (Latin only — never set Cyrillic in it) or the Cormorant caps
 * fallback with an arch over the I. Any other brand name from config is set in Manrope with the accent dot.
 */
export function Logo({ name, size = 22, variant = "blackletter" }: { name: string; size?: number; variant?: "blackletter" | "serif" | "sans" }) {
  if (name.toUpperCase() === "SIFT" && variant !== "sans") return <Wordmark variant={variant} size={variant === "blackletter" ? size * 1.3 : size} />;
  return (
    <span className="inline-flex items-center font-display font-extrabold tracking-[-0.03em]" style={{ fontSize: size, lineHeight: 1 }}>
      {name}
      <span className="ml-[0.06em] inline-block rounded-full bg-accent" style={{ width: size * 0.2, height: size * 0.2 }} />
    </span>
  );
}
