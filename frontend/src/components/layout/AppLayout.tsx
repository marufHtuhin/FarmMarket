import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronDown, LogOut, Menu, User } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { conversationsApi, notificationsApi } from "../../services/api";
import { LanguageToggle, Logo } from "./brand";
import { SidebarNav, navForRole } from "./nav";
import { Drawer } from "../ui/misc";
import { BottomNav } from "./BottomNav";
import { EmailVerificationBanner } from "./EmailVerificationBanner";

function UserMenu() {
  const { user, logout } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  if (!user) return null;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full border border-line bg-white py-1.5 pl-1.5 pr-3 text-sm font-bold text-ink hover:border-leaf"
      >
        <span className="grid h-8 w-8 place-items-center rounded-full bg-leaf text-sm font-extrabold text-white">
          {user.name.charAt(0).toUpperCase()}
        </span>
        <span className="hidden max-w-[140px] truncate sm:block">{user.name}</span>
        <ChevronDown className="h-4 w-4 text-muted" />
      </button>
      {open && (
        <>
          <button type="button" aria-label="Close menu" className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-56 overflow-hidden rounded-2xl border border-line bg-white shadow-lift">
            <div className="border-b border-line px-4 py-3">
              <p className="truncate text-sm font-bold">{user.name}</p>
              <p className="truncate text-xs text-muted">{user.email}</p>
              <p className="mt-1 text-xs font-semibold capitalize text-leaf">{t(`role${user.role[0].toUpperCase()}${user.role.slice(1)}`)}</p>
            </div>
            <Link
              to="/profile"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-4 py-3 text-sm font-semibold hover:bg-cream"
            >
              <User className="h-4 w-4" /> {t("navProfile")}
            </Link>
            <button
              type="button"
              onClick={async () => {
                setOpen(false);
                await logout();
                navigate("/login");
              }}
              className="flex w-full items-center gap-2 px-4 py-3 text-sm font-semibold text-red-700 hover:bg-cream"
            >
              <LogOut className="h-4 w-4" /> {t("logout")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function NotificationBell() {
  const { user } = useAuth();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: notificationsApi.list,
    enabled: !!user,
    staleTime: 60_000,
    retry: false,
  });
  const unread = (data || []).filter((n) => !n.is_read).length;
  return (
    <Link
      to="/notifications"
      aria-label="Notifications"
      className="relative grid h-10 w-10 place-items-center rounded-full border border-line bg-white text-ink hover:border-leaf"
    >
      <Bell className="h-5 w-5" />
      {unread > 0 && (
        <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-marigold px-1 text-[10px] font-extrabold text-[#2e2110]">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}

export function Topbar({ onMenu }: { onMenu?: () => void }) {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-cream/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
        {onMenu && (
          <button
            type="button"
            onClick={onMenu}
            aria-label="Open menu"
            className="grid h-10 w-10 place-items-center rounded-full border border-line bg-white lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
        <Link to="/" className="lg:hidden">
          <Logo compact />
        </Link>
        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <LanguageToggle />
          <NotificationBell />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

export function AppLayout() {
  const { user } = useAuth();
  const { t } = useLang();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const qc = useQueryClient();

  // Unread-message badge for the nav (farmer/buyer only). Refetched on every
  // navigation so the badge clears as soon as a thread is read elsewhere.
  const canChat = user?.role === "farmer" || user?.role === "buyer";
  const unreadQ = useQuery({
    queryKey: ["conversations", "unread"],
    queryFn: conversationsApi.unreadCount,
    enabled: !!user && canChat,
    staleTime: 0,
    retry: false,
  });
  useEffect(() => {
    if (canChat) qc.invalidateQueries({ queryKey: ["conversations", "unread"] });
  }, [location.pathname, canChat, qc]);

  const entries = navForRole(user?.role).map((e) =>
    e.to === "/messages" ? { ...e, badge: unreadQ.data?.unread ?? 0 } : e
  );

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col bg-forest lg:flex">
        <Link to="/" className="flex items-center gap-2.5 px-5 py-5">
          <Logo light />
        </Link>
        <div className="thin-scroll flex-1 overflow-y-auto">
          <SidebarNav entries={entries} />
        </div>
        <div className="border-t border-white/10 px-5 py-4 text-xs leading-relaxed text-white/60">
          <p className="font-display font-bold text-white/85">FarmMarket</p>
          <p>FastAPI · MySQL · scikit-learn · OpenStreetMap</p>
        </div>
      </aside>

      {/* Mobile drawer (role-aware) */}
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="FarmMarket">
        <nav className="flex flex-col gap-1">
          {entries.map((e) => (
            <Link
              key={e.to}
              to={e.to}
              onClick={() => setDrawerOpen(false)}
              className="flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-sm font-semibold text-ink hover:bg-mint"
            >
              <e.icon className="h-5 w-5 text-leaf" />
              <span className="flex-1">{t(e.labelKey)}</span>
              {e.badge ? (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-marigold px-1.5 text-[11px] font-extrabold text-[#2e2110]">
                  {e.badge > 99 ? "99+" : e.badge}
                </span>
              ) : null}
            </Link>
          ))}
        </nav>
      </Drawer>

      <div className="lg:pl-64">
        <Topbar onMenu={() => setDrawerOpen(true)} />
        <main className="mx-auto max-w-7xl px-4 pb-28 pt-5 sm:px-6 lg:pb-10">
          <EmailVerificationBanner />
          <Outlet />
        </main>
      </div>
      <BottomNav />
    </div>
  );
}
