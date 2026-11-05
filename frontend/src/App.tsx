import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Route, Routes, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { BottomNav } from "./components/BottomNav";
import { Logo } from "./components/Logo";
import { Splash } from "./components/Splash";
import { Toaster } from "./components/Toaster";
import { routeEnter } from "./lib/motion";
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
import Item from "./pages/Item";
import Gifts from "./pages/Gifts";
import GiftRedeem from "./pages/GiftRedeem";
import SharedFind from "./pages/SharedFind";
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

/**
 * Deep links: t.me/<bot>/app?startapp=search_<uuid>, f_<token> (shared find), g_<code> (gift),
 * or a named screen. The server already attributed the referral for f_/g_ at sign-up.
 */
function useStartParam() {
  const navigate = useNavigate();
  useEffect(() => {
    const p = startParam();
    if (!p) return;
    const m = /^search[_/]([0-9a-f-]{36})$/i.exec(p);
    if (m) navigate(`/search/${m[1]}`, { replace: true });
    else if (/^f_[\w-]{4,32}$/.test(p)) navigate(`/find/${p.slice(2)}`, { replace: true });
    else if (/^g_[\w-]{4,32}$/.test(p)) navigate(`/gift/${p.slice(2)}`, { replace: true });
    else if (["subscription", "referral", "history", "saved", "gifts"].includes(p)) navigate(`/${p}`, { replace: true });
    else if (p === "watches") navigate("/saved?tab=watch", { replace: true });
  }, [navigate]);
}

/** Scroll position per history entry: back to results lands where the user left. New screens start at the top. */
function useScrollMemory() {
  const loc = useLocation();
  const type = useNavigationType();
  const saved = useRef(new Map<string, number>());
  const prev = useRef(loc.key);
  useLayoutEffect(() => {
    const map = saved.current;
    if (type === "POP") {
      const y = map.get(loc.key) ?? 0;
      let tries = 0;
      const restore = () => {
        window.scrollTo(0, y);
        if (Math.abs(window.scrollY - y) > 2 && tries++ < 20) requestAnimationFrame(restore);
      };
      restore();
    } else window.scrollTo(0, 0);
    prev.current = loc.key;
    const onScroll = () => map.set(prev.current, window.scrollY);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [loc.key, type]);
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
  useScrollMemory();
  const reduce = useReducedMotion();
  const location = useLocation();
  const minSplash = useMinDelay(splashSeen() ? 0 : 2000);

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
      {/* The item screen skips the fade: its photo flies in from the tapped card (shared layoutId). */}
      <motion.div key={pathname.includes("/item/") ? "item" : pathname}
        initial={reduce || pathname.includes("/item/") ? false : routeEnter.initial} animate={routeEnter.animate} transition={routeEnter.transition}>
      <Routes location={location}>
        <Route path="/" element={<Home />} />
        <Route path="/search/:id" element={<SearchPage />} />
        <Route path="/search/:sid/item/:pid" element={<Item />} />
        <Route path="/find/:token" element={<SharedFind />} />
        <Route path="/gift/:code" element={<GiftRedeem />} />
        <Route path="/gifts" element={<Gifts />} />
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
      </motion.div>
      {showNav && <BottomNav />}
      <Toaster />
    </div>
    </>
  );
}

/** Splash holds for its ~2 s ritual on the first open of a session only. */
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
