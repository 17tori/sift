import { motion, useAnimationControls } from "motion/react";
import { useEffect, useRef } from "react";
import { NavLink } from "react-router-dom";
import { useMe } from "../lib/queries";
import { spring } from "../lib/motion";
import { haptic } from "../lib/telegram";
import { IconClock, IconHeart, IconSearch, IconUser } from "./icons";
import { cx } from "./ui";

const ITEMS = [
  { to: "/", label: "Поиск", Icon: IconSearch, end: true, fill: false },
  { to: "/saved", label: "Избранное", Icon: IconHeart, end: false, fill: true },
  { to: "/history", label: "История", Icon: IconClock, end: false, fill: false },
  { to: "/profile", label: "Профиль", Icon: IconUser, end: false, fill: false },
];

/** Count on the Favorites tab; bounces when it grows (choreography VI). */
function FavBadge() {
  const { data: me } = useMe();
  const n = me?.favorites_count ?? 0;
  const prev = useRef(n);
  const controls = useAnimationControls();
  useEffect(() => {
    if (n > prev.current) controls.start({ y: [-4, 0], scale: [1.2, 1], transition: spring.bouncy });
    prev.current = n;
  }, [n, controls]);
  if (!n) return null;
  return (
    <motion.span animate={controls}
      className="absolute -top-1 left-[15px] grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 font-mono text-[10px] leading-none text-white">
      {n > 99 ? "99+" : n}
    </motion.span>
  );
}

export function BottomNav() {
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg">
      <div className="mx-auto flex max-w-xl">
        {ITEMS.map(({ to, label, Icon, end, fill }) => (
          <NavLink key={to} to={to} end={end} onClick={() => haptic.select()}
            className={({ isActive }) => cx("relative flex flex-1 flex-col items-center gap-1 pt-[11px] pb-2 text-[11px] font-medium transition-colors",
              isActive ? "text-ink" : "text-ink-3")}>
            {({ isActive }) => (
              <>
                {isActive && <motion.span layoutId="nav-indicator" className="absolute -top-px h-0.5 w-5 bg-ink" transition={spring.soft} />}
                <span className="relative">
                  <Icon size={23} strokeWidth={isActive ? 2 : 1.75} {...(fill ? { filled: isActive } : {})} />
                  {to === "/saved" && <FavBadge />}
                </span>
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
