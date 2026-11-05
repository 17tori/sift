/* Wordmark with custom S geometry (no magnifier/cart/bag tropes). */
export function Logo({ name, size = 22 }: { name: string; size?: number }) {
  const rest = name.slice(1);
  const isSift = name.toUpperCase() === "SIFT";
  return (
    <span className="inline-flex items-center font-display font-extrabold tracking-[0.08em]" style={{ fontSize: size, lineHeight: 1 }}>
      {isSift ? (
        <>
          <svg width={size * 0.72} height={size} viewBox="0 0 18 25" aria-hidden className="mr-[0.06em]">
            <path d="M15.5 5.2C14 3.4 11.8 2.5 9.2 2.5 5.4 2.5 3 4.5 3 7.3c0 6.4 12.6 3.8 12.6 9.9 0 2.9-2.6 5.1-6.6 5.1-2.8 0-5.2-1-7-2.8"
              fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="square" />
          </svg>
          <span>{rest}</span>
        </>
      ) : (
        <span>{name}</span>
      )}
      <span className="ml-[0.08em] inline-block bg-accent" style={{ width: size * 0.22, height: size * 0.22 }} />
    </span>
  );
}
