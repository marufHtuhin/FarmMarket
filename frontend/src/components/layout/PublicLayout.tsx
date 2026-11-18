import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { LanguageToggle, Logo } from "./brand";
import { Button } from "../ui/core";

export function PublicLayout() {
  const { user } = useAuth();
  const { t } = useLang();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-line bg-cream/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
          <Link to="/">
            <Logo />
          </Link>
          {/* Nav appears at lg (1024px), not md: at 768px the five links +
              full logo + language toggle + Login/Join total ~827px, wider
              than the viewport (audit found scrollWidth 827px > 768px on
              all public pages). Below lg the public pages already rely on
              in-page/footer links, as on mobile. */}
          <nav className="ml-6 hidden items-center gap-1 text-sm font-semibold text-ink lg:flex">
            <Link to="/marketplace" className="rounded-full px-3 py-2 hover:bg-mint">
              {t("navMarket")}
            </Link>
            <Link to="/prices" className="rounded-full px-3 py-2 hover:bg-mint">
              {t("navPrices")}
            </Link>
            <Link to="/how-it-works" className="rounded-full px-3 py-2 hover:bg-mint">
              {t("navHowItWorks")}
            </Link>
            <Link to="/about" className="rounded-full px-3 py-2 hover:bg-mint">
              {t("navAbout")}
            </Link>
            <Link to="/verify" className="rounded-full px-3 py-2 hover:bg-mint">
              {t("navVerify")}
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <LanguageToggle />
            {user ? (
              <Link to="/dashboard">
                <Button size="sm">{t("dashboard")}</Button>
              </Link>
            ) : (
              <>
                <Link to="/login" className="hidden sm:block">
                  <Button variant="ghost" size="sm">
                    {t("login")}
                  </Button>
                </Link>
                <Link to="/register">
                  <Button size="sm">{t("join")}</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>
      <footer className="bg-forest text-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-3">
          <div>
            <Logo light />
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-white/75">{t("footerText")}</p>
          </div>
          <div className="text-sm">
            <p className="font-display font-bold">{t("navMarket")}</p>
            <ul className="mt-3 space-y-2 text-white/75">
              <li>
                <Link to="/marketplace" className="hover:text-white">
                  {t("marketplace")}
                </Link>
              </li>
              <li>
                <Link to="/prices" className="hover:text-white">
                  {t("navPrices")}
                </Link>
              </li>
              <li>
                <Link to="/verify" className="hover:text-white">
                  {t("navVerify")}
                </Link>
              </li>
            </ul>
          </div>
          <div className="text-sm">
            <p className="font-display font-bold">{t("builtWith")}</p>
            <p className="mt-3 text-white/75">{t("stackCredits")}</p>
            <p className="mt-2 text-xs text-white/50">{t("footerNote")}</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
