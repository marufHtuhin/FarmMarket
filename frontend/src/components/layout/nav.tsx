import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Store,
  Sprout,
  ClipboardList,
  PlusCircle,
  Award,
  LineChart,
  Handshake,
  Package,
  MessageSquareHeart,
  Truck,
  QrCode,
  Bell,
  User,
  ShieldCheck,
  Users,
  Database,
  ScrollText,
  PackageCheck,
  Car,
  ScanLine,
  CloudSun,
  MessageSquare,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";
import type { Role } from "../../services/api";

export interface NavEntry {
  to: string;
  labelKey: string;
  icon: LucideIcon;
  roles?: Role[];
  end?: boolean;
  /** Unread count badge, attached by AppLayout (messages only). */
  badge?: number;
}

export const NAV_ENTRIES: NavEntry[] = [
  { to: "/dashboard", labelKey: "dashboard", icon: LayoutDashboard, end: true },
  { to: "/marketplace", labelKey: "navMarket", icon: Store },
  { to: "/matches", labelKey: "navMatches", icon: Handshake },
  { to: "/prices", labelKey: "navPrices", icon: LineChart },
  { to: "/weather", labelKey: "navWeather", icon: CloudSun },
  { to: "/orders", labelKey: "navOrders", icon: Package },
  { to: "/offers", labelKey: "navOffers", icon: ClipboardList },
  { to: "/messages", labelKey: "navMessages", icon: MessageSquare, roles: ["farmer", "buyer"] },
  { to: "/farms", labelKey: "navFarms", icon: Sprout, roles: ["farmer"] },
  { to: "/listings/mine", labelKey: "navListings", icon: ClipboardList, roles: ["farmer"] },
  { to: "/listings/new", labelKey: "navNewListing", icon: PlusCircle, roles: ["farmer"] },
  { to: "/quality", labelKey: "navQuality", icon: Award, roles: ["farmer"] },
  { to: "/deliveries", labelKey: "navDeliveries", icon: PackageCheck, roles: ["transporter"] },
  { to: "/vehicles", labelKey: "navVehicles", icon: Car, roles: ["transporter"] },
  { to: "/assistant", labelKey: "navAssistant", icon: MessageSquareHeart },
  { to: "/logistics", labelKey: "navLogistics", icon: Truck },
  { to: "/batches", labelKey: "navBatches", icon: QrCode },
  { to: "/verify", labelKey: "navVerify", icon: ScanLine },
  { to: "/notifications", labelKey: "notifications", icon: Bell },
  { to: "/profile", labelKey: "navProfile", icon: User },
  { to: "/admin", labelKey: "navAdmin", icon: ShieldCheck, roles: ["admin"], end: true },
  { to: "/admin/users", labelKey: "navAdminUsers", icon: Users, roles: ["admin"] },
  { to: "/admin/data-sources", labelKey: "navDataSources", icon: Database, roles: ["admin"] },
  { to: "/admin/audit-logs", labelKey: "navAuditLogs", icon: ScrollText, roles: ["admin"] },
];

export function navForRole(role: Role | undefined): NavEntry[] {
  if (!role) return NAV_ENTRIES.filter((e) => !e.roles);
  return NAV_ENTRIES.filter((e) => !e.roles || e.roles.includes(role));
}

export function SidebarNav({ entries, onNavigate }: { entries?: NavEntry[]; onNavigate?: () => void }) {
  const { t } = useLang();
  const list = entries ?? NAV_ENTRIES;
  return (
    <nav className="flex flex-col gap-1 px-3 py-4">
      {list.map((e) => (
        <NavLink
          key={e.to}
          to={e.to}
          end={e.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-sm font-semibold transition ${
              isActive ? "bg-white/15 text-white" : "text-white/75 hover:bg-white/10 hover:text-white"
            }`
          }
        >
          <e.icon className="h-5 w-5 shrink-0" />
          <span className="flex-1 truncate">{t(e.labelKey)}</span>
          {e.badge ? (
            <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-marigold px-1.5 text-[11px] font-extrabold text-[#2e2110]">
              {e.badge > 99 ? "99+" : e.badge}
            </span>
          ) : null}
        </NavLink>
      ))}
    </nav>
  );
}
