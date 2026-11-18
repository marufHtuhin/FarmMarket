import { NavLink } from "react-router-dom";
import { Store, Handshake, LineChart, Package, Menu } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";

const ITEMS = [
  { to: "/marketplace", labelKey: "navMarket", icon: Store },
  { to: "/matches", labelKey: "navMatches", icon: Handshake },
  { to: "/prices", labelKey: "navPrices", icon: LineChart },
  { to: "/orders", labelKey: "navOrders", icon: Package },
  { to: "/profile", labelKey: "navMenu", icon: Menu },
];

export function BottomNav() {
  const { t } = useLang();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
      <div className="grid grid-cols-5">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-bold transition ${
                isActive ? "text-leaf" : "text-muted hover:text-ink"
              }`
            }
          >
            <item.icon className="h-5 w-5" />
            {/* min-w-0 lets the label shrink below its content width so
                truncate can clip it: without it "Marketplace" overflowed its
                72px cell by 3px on a 360px viewport (measured left=-3). */}
            <span className="min-w-0 max-w-full truncate px-1">{t(item.labelKey)}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
