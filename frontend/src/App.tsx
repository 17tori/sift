import { AnimatePresence } from "motion/react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { BottomNav } from "./components/BottomNav";
import { Logo } from "./components/Logo";
import { Splash } from "./components/Splash";
import { Spinner } from "./components/ui";
import { ApiError } from "./lib/api";
import { useConfig, useMe } from "./lib/queries";
import { backButton, insideTelegram, paintChrome, startParam, telegramScheme, tg } from "./lib/telegram";
import Home from "./pages/Home";
import SearchPage from "./pages/SearchPage";
import Saved from "./pages/Saved";
import History from "./pages/History";
import Profile from "./pages/Profile";
import Subscription from "./pages/Subscription";
import Settings from "./pages/Settings";
import Support from "./pages/Support";
import Referral from "./pages/Referral";
const Admin = lazy(() => import("./pages/admin/Admin"));

const TABS = new Set(["/", "/saved", "/history", "/profile"]);
const BG = { light: "#F5F3EE", dark: "#111111" } as const;

function useTheme(pref: "system" | "light" | "dark" | undefined) {
  useEffect(() => {
    const apply = () => {
      const mode = !pref || pref === "system" ? telegramScheme() : pref;
      document.documentElement.dataset.theme = mode;
      document.documentElement.style.colorScheme = mode;
      paintChrome(BG[mode]);
    };
    apply();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    tg?.onEvent("themeChanged", apply);
    mq.addEventListener("change", apply);
    return () => {
      tg?.offEvent("themeChanged", apply);
      mq.removeEventListener("change", apply);
    };
  }, [pref]);
}

function useAccent(accent: string | undefined) {
  useEffect(() => {
    if (!accent || !/^#[0-9a-f]{6}$/i.test(accent)) return;
    const root = document.documentElement.style;
    root.setProperty("--accent", accent);
    root.setProperty("--accent-soft", `color-mix(in srgb, ${accent} 12%, transparent)`);
  }, [accent]);
}

/** Telegram BackButton on every non-tab screen. */
function useBack() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (TABS.has(pathname)) return backButton(null);
    return backButton(() => (window.history.length > 1 ? navigate(-1) : navigate("/", { replace: true })));
  }, [pathname, navigate]);
}

/** Deep links: t.me/<bot>/app?startapp=search_<uuid> or a WebApp URL with path /search/<uuid>. */
function useStartParam() {
  const navigate = useNavigate();
  useEffect(() => {
    const p = startParam();
    if (!p) return;
    const m = /^search[_/]([0-9a-f-]{36})$/i.exec(p);
    if (m) navigate(`/search/${m[1]}`, { replace: true });
    else if (p === "subscription" || p === "referral" || p === "history" || p === "saved") navigate(`/${p}`, { replace: true });
  }, [navigate]);
}

function OutsideTelegram({ name, bot }: { name: string; bot?: string }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-6 px-8 text-center">
      <Logo name={name} size={28} />
      <p className="max-w-xs text-sm text-ink-2">Приложение работает внутри Telegram. Откройте его через бота.</p>
      {bot && (
        <a className="rounded-2xl bg-accent px-5 py-3 text-sm font-semibold text-accent-ink" href={`https://t.me/${bot}`}>
          Открыть @{bot}
        </a>
      )}
    </div>
  );
}

function Blocked() {
  return (
    <div className="flex min-h-dvh items-center justify-center px-8 text-center text-sm text-ink-2">
      Доступ к аккаунту ограничен. Напишите в поддержку через бота.
    </div>
  );
}

export default function App() {
  const config = useConfig();
  const me = useMe();
  const { pathname } = useLocation();
  useTheme(me.data?.preferences.theme);
  useAccent(config.data?.brand.accent);
  useBack();
  useStartParam();
  const minSplash = useMinDelay(splashSeen() ? 0 : 900);

  useEffect(() => {
    if (config.data) document.title = config.data.brand.name;
  }, [config.data]);

  const name = config.data?.brand.name ?? "SIFT";
  const splash = <AnimatePresence>{(me.isPending || !minSplash) && <Splash key="splash" />}</AnimatePresence>;
  if (!insideTelegram() && !import.meta.env.DEV) return <OutsideTelegram name={name} bot={config.data?.bot_username} />;
  if (me.error instanceof ApiError && me.error.status === 403) return <Blocked />;

  if (me.isPending) return splash;

  const showNav = TABS.has(pathname);
  return (
    <>
    {splash}
    <div className="mx-auto min-h-dvh max-w-xl pt-[var(--tg-safe-top,0px)]" style={{ paddingBottom: showNav ? "calc(76px + var(--tg-safe-bottom, 0px))" : "var(--tg-safe-bottom, 0px)" }}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/search/:id" element={<SearchPage />} />
        <Route path="/saved" element={<Saved />} />
        <Route path="/history" element={<History />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/subscription" element={<Subscription />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/support" element={<Support />} />
        <Route path="/referral" element={<Referral />} />
        <Route path="/admin/*" element={<Suspense fallback={<div className="flex justify-center py-20"><Spinner /></div>}><Admin /></Suspense>} />
        <Route path="*" element={<Home />} />
      </Routes>
      {showNav && <BottomNav />}
    </div>
    </>
  );
}

/** Splash holds for its 900 ms ritual on the first open of a session only. */
function useMinDelay(ms: number): boolean {
  const [done, setDone] = useState(ms === 0);
  useEffect(() => {
    if (ms === 0) return;
    const id = window.setTimeout(() => { setDone(true); try { sessionStorage.setItem("sift.splash", "1"); } catch { /* private mode */ } }, ms);
    return () => window.clearTimeout(id);
  }, [ms]);
  return done;
}

function splashSeen(): boolean {
  try { return !!sessionStorage.getItem("sift.splash"); } catch { return true; }
}
