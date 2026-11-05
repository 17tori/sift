import { NavLink } from "react-router-dom";
import { haptic } from "../lib/telegram";
import { IconClock, IconHeart, IconSearch, IconUser } from "./icons";
import { cx } from "./ui";

const ITEMS = [
  { to: "/", label: "Поиск", Icon: IconSearch, end: true },
  { to: "/saved", label: "Избранное", Icon: IconHeart, end: false },
  { to: "/history", label: "История", Icon: IconClock, end: false },
  { to: "/profile", label: "Профиль", Icon: IconUser, end: false },
];

export function BottomNav() {
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-xl">
        {ITEMS.map(({ to, label, Icon, end }) => (
          <NavLink key={to} to={to} end={end} onClick={() => haptic.select()}
            className={({ isActive }) => cx("flex flex-1 flex-col items-center gap-1 pt-2.5 pb-2 text-[11px] font-medium transition-colors",
              isActive ? "text-ink" : "text-ink-3")}>
            {({ isActive }) => (
              <>
                <Icon size={23} strokeWidth={isActive ? 2 : 1.6} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
