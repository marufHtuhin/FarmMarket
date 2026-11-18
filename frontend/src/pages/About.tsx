import { Link } from "react-router-dom";
import { Sprout, Store, Truck } from "lucide-react";
import { useLang } from "../i18n/LanguageContext";
import { Card, PageHeader } from "../components/ui/core";

export function AboutPage() {
  const { t } = useLang();
  return (
    <div className="mx-auto max-w-3xl py-4">
      <PageHeader title={t("aboutTitle")} />
      <Card className="space-y-4 p-6 text-[15px] leading-[1.9] text-[#4c5f52] sm:p-8">
        <p>{t("aboutText1")}</p>
        <p>{t("aboutText2")}</p>
        <p>{t("aboutText3")}</p>
        <p className="text-sm text-muted">{t("footerNote")}</p>
      </Card>
    </div>
  );
}

export function HowItWorksPage() {
  const { t } = useLang();
  const cards = [
    { icon: <Sprout className="h-6 w-6" />, title: t("howFarmerTitle"), text: t("howFarmerText"), cta: "/register", ctaLabel: t("join") },
    { icon: <Store className="h-6 w-6" />, title: t("howBuyerTitle"), text: t("howBuyerText"), cta: "/marketplace", ctaLabel: t("exploreMarket") },
    { icon: <Truck className="h-6 w-6" />, title: t("howTransporterTitle"), text: t("howTransporterText"), cta: "/register", ctaLabel: t("join") },
  ];
  return (
    <div className="mx-auto max-w-4xl py-4">
      <PageHeader title={t("howTitle")} />
      <div className="grid gap-5 md:grid-cols-3">
        {cards.map((c) => (
          <Card key={c.title} className="flex flex-col p-6">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-mint text-leaf">{c.icon}</span>
            <h2 className="mt-4 font-display text-lg font-extrabold text-forest">{c.title}</h2>
            <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{c.text}</p>
            <Link to={c.cta} className="mt-4 text-sm font-bold text-leaf hover:underline">
              {c.ctaLabel} →
            </Link>
          </Card>
        ))}
      </div>
      <Card className="mt-6 p-6">
        <h2 className="font-display text-lg font-extrabold text-forest">{t("howItWorksTitle")}</h2>
        <ol className="mt-4 space-y-3 text-sm leading-relaxed text-muted">
          <li>
            <b className="text-ink">1. {t("step1Title")} —</b> {t("step1Text")}
          </li>
          <li>
            <b className="text-ink">2. {t("step2Title")} —</b> {t("step2Text")}
          </li>
          <li>
            <b className="text-ink">3. {t("step3Title")} —</b> {t("step3Text")}
          </li>
        </ol>
      </Card>
    </div>
  );
}
