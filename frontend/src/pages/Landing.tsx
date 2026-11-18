import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Handshake, MapPin, ShieldCheck, TrendingUp, Leaf, Truck, QrCode } from "lucide-react";
import { productsApi, pricesApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { HERO_PHOTO } from "../utils/crops";
import { ProductCard } from "../components/ProductCard";
import { Button, Spinner } from "../components/ui/core";
import { useAuth } from "../contexts/AuthContext";

export function LandingPage() {
  const { t, fmtNum } = useLang();
  const { user } = useAuth();
  const productsQ = useQuery({ queryKey: ["products", "landing"], queryFn: () => productsApi.list() });
  const pricesQ = useQuery({ queryKey: ["prices", "landing"], queryFn: () => pricesApi.list() });

  const products = productsQ.data || [];
  const prices = pricesQ.data || [];
  const districts = new Set([...products.map((p) => p.district), ...prices.map((p) => p.district)]).size;

  return (
    <div className="space-y-12 py-4">
      {/* Hero */}
      <section className="relative grid items-center gap-8 overflow-hidden rounded-[28px] border border-[#f0e8d3] bg-[#fffdf8] px-6 py-9 shadow-card sm:px-10 sm:py-12 lg:grid-cols-[1.05fr_.95fr]">
        <div className="min-w-0">
          <span className="inline-flex items-center gap-2 rounded-full bg-sand px-3.5 py-1.5 text-xs font-extrabold text-[#8a5a12]">
            <span className="h-2 w-2 rounded-full bg-leaf" />
            {t("heroEyebrow")}
          </span>
          <h1
            className="mt-5 font-display text-4xl font-extrabold leading-[1.18] tracking-tight text-forest sm:text-5xl lg:text-[3.35rem]"
            dangerouslySetInnerHTML={{ __html: t("heroTitle") }}
          />
          <p className="mt-4 max-w-[560px] text-[15px] leading-[1.8] text-[#4c5f52] sm:text-[17px]">{t("heroText")}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/marketplace">
              <Button size="lg">
                {t("exploreMarket")} <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            {!user && (
              <Link to="/register">
                <Button variant="secondary" size="lg">
                  {t("getStarted")}
                </Button>
              </Link>
            )}
            {user && (
              <Link to="/dashboard">
                <Button variant="secondary" size="lg">
                  {t("dashboard")}
                </Button>
              </Link>
            )}
          </div>
          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-[13px] font-semibold text-muted">
            <span className="inline-flex items-center gap-1.5">
              <Handshake className="h-4 w-4 text-leaf" /> {t("proof1")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-leaf" /> {t("proof2")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-leaf" /> {t("proof3")}
            </span>
          </div>
        </div>
        <div className="relative">
          <div className="rotate-1 overflow-hidden rounded-[26px] shadow-2xl">
            <img src={HERO_PHOTO} alt="Fresh produce at a bazar" className="h-[300px] w-full object-cover sm:h-[360px]" />
            <span className="absolute right-4 top-4 rounded-full bg-white/90 px-3.5 py-1.5 text-xs font-extrabold text-forest shadow backdrop-blur">
              {t("freshHarvest")}
            </span>
          </div>
          <div className="floaty absolute -left-2 top-8 flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-xl sm:-left-6">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sand text-xl">🍅</span>
            <div>
              <b className="block text-sm leading-tight text-ink">{t("heroPriceCrop")}</b>
              <span className="block text-[11px] text-muted">{t("heroPriceNote")}</span>
            </div>
            <b className="ml-1 whitespace-nowrap font-display text-lg text-leaf">{t("heroPriceValue")}</b>
          </div>
        </div>
      </section>

      {/* Live stats */}
      <section>
        <h2 className="font-display text-xl font-extrabold text-forest">{t("liveStats")}</h2>
        <div className="mt-4 grid grid-cols-3 gap-3">
          {[
            { label: t("productsCount"), value: productsQ.isLoading ? "…" : fmtNum(products.length, 0), icon: <Leaf className="h-5 w-5" /> },
            { label: t("priceRecordsCount"), value: pricesQ.isLoading ? "…" : fmtNum(prices.length, 0), icon: <TrendingUp className="h-5 w-5" /> },
            { label: t("districtsCount"), value: productsQ.isLoading ? "…" : fmtNum(districts, 0), icon: <MapPin className="h-5 w-5" /> },
          ].map((s) => (
            <div key={s.label} className="rounded-3xl border border-line bg-white p-4 shadow-card sm:p-5">
              <span className="grid h-10 w-10 place-items-center rounded-2xl bg-mint text-leaf">{s.icon}</span>
              <b className="mt-3 block font-display text-2xl font-extrabold text-forest sm:text-3xl">{s.value}</b>
              <span className="text-[13px] font-semibold text-muted">{s.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Featured listings */}
      <section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-2xl font-extrabold text-forest">{t("featuredListings")}</h2>
          <Link to="/marketplace">
            <Button variant="secondary" size="sm">
              {t("browseAll")} <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
        {productsQ.isLoading ? (
          <Spinner label={t("loading")} />
        ) : products.length === 0 ? (
          <p className="mt-4 rounded-3xl border border-dashed border-line bg-white/60 p-8 text-center text-muted">{t("noProducts")}</p>
        ) : (
          <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {products.slice(0, 6).map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        )}
      </section>

      {/* How it works strip */}
      <section className="rounded-[28px] bg-forest px-6 py-10 text-white sm:px-10">
        <h2 className="font-display text-2xl font-extrabold">{t("howItWorksTitle")}</h2>
        <div className="mt-6 grid gap-6 md:grid-cols-3">
          {[
            { n: "1", title: t("step1Title"), text: t("step1Text") },
            { n: "2", title: t("step2Title"), text: t("step2Text") },
            { n: "3", title: t("step3Title"), text: t("step3Text") },
          ].map((s) => (
            <div key={s.n} className="rounded-3xl bg-white/10 p-5">
              <span className="grid h-10 w-10 place-items-center rounded-full bg-marigold font-display text-lg font-extrabold text-[#2e2110]">
                {s.n}
              </span>
              <h3 className="mt-3 font-display text-lg font-bold">{s.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-white/75">{s.text}</p>
            </div>
          ))}
        </div>
        <Link to="/how-it-works" className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-marigold hover:underline">
          {t("navHowItWorks")} <ArrowRight className="h-4 w-4" />
        </Link>
      </section>

      {/* Trust strip */}
      <section className="grid gap-4 sm:grid-cols-3">
        {[
          { icon: <Handshake className="h-6 w-6" />, title: t("trust1"), sub: t("trust1s") },
          { icon: <MapPin className="h-6 w-6" />, title: t("trust2"), sub: t("trust2s") },
          { icon: <QrCode className="h-6 w-6" />, title: t("trust3"), sub: t("trust3s") },
        ].map((x) => (
          <div key={x.title} className="flex items-start gap-4 rounded-3xl border border-line bg-white p-5 shadow-card">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-mint text-leaf">{x.icon}</span>
            <div>
              <h3 className="font-display font-bold text-ink">{x.title}</h3>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">{x.sub}</p>
            </div>
          </div>
        ))}
      </section>

      {/* Dispatch teaser */}
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-[28px] border border-line bg-white p-6 shadow-card sm:p-8">
        <div className="flex min-w-0 items-start gap-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-sand text-marigold">
            <Truck className="h-6 w-6" />
          </span>
          <div>
            <h3 className="font-display text-lg font-extrabold text-forest">{t("ti_logisticsTitle")}</h3>
            <p className="mt-1 max-w-xl text-sm text-muted">{t("logisticsSub")}</p>
          </div>
        </div>
        <Link to="/logistics">
          <Button>{t("planRoutes")}</Button>
        </Link>
      </section>
    </div>
  );
}
