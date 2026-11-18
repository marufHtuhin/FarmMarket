import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BadgeCheck, MapPin, ShoppingCart, Handshake } from "lucide-react";
import { productsApi, pricesApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useAuth } from "../contexts/AuthContext";
import { productEmoji, productPhoto } from "../utils/crops";
import { apiErrorMessage, unitLabel } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, Spinner } from "../components/ui/core";
import { Badge } from "../components/ui/misc";
import { OrderModal } from "../components/OrderModal";
import { OfferModal } from "../components/OfferModal";
import { MessageButton } from "../components/MessageButton";

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);
  const { t, fmtNum, lang } = useLang();
  const { user } = useAuth();
  const [orderOpen, setOrderOpen] = useState(false);
  const [offerOpen, setOfferOpen] = useState(false);

  // GET /products/{id} is in the shared contract; fall back to the list if the
  // backend has not shipped it yet.
  const q = useQuery({
    queryKey: ["product", productId],
    queryFn: async () => {
      try {
        return await productsApi.get(productId);
      } catch (e) {
        const status = (e as { response?: { status?: number } }).response?.status;
        if (status === 404) {
          const list = await productsApi.list();
          const found = list.find((p) => p.id === productId);
          if (found) return found;
        }
        throw e;
      }
    },
    enabled: Number.isFinite(productId),
    retry: false,
  });

  const pricesQ = useQuery({
    queryKey: ["prices", q.data?.name],
    queryFn: () => pricesApi.list({ product_name: q.data?.name }),
    enabled: !!q.data?.name,
    retry: false,
  });

  if (q.isLoading) return <Spinner label={t("loading")} />;
  if (q.isError) return <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />;
  const p = q.data;
  if (!p) return <EmptyState title={t("productNotFound")} action={<Link to="/marketplace"><Button variant="secondary">{t("back")}</Button></Link>} />;

  const imgSrc =
    p.image_url && /^https?:\/\//i.test(p.image_url) ? p.image_url : p.images?.[0]?.url || productPhoto(p.name);
  const marketPrices = (pricesQ.data || []).filter((r) => r.product_name.toLowerCase() === p.name.toLowerCase());
  const latestMarket = marketPrices
    .filter((r) => r.recorded_at)
    .sort((a, b) => new Date(b.recorded_at || 0).getTime() - new Date(a.recorded_at || 0).getTime())[0];

  return (
    <div>
      <Link to="/marketplace" className="mb-4 inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
        <ArrowLeft className="h-4 w-4" /> {t("back")}
      </Link>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="relative h-72 overflow-hidden rounded-3xl bg-gradient-to-br from-[#e7f3e8] via-[#f6f3e2] to-[#fdf3d7] sm:h-96">
          <span className="absolute inset-0 grid place-items-center text-8xl">{productEmoji(p.name)}</span>
          {imgSrc && (
            <img
              src={imgSrc}
              alt={p.name}
              className="absolute inset-0 h-full w-full object-cover"
              onError={(e) => (e.currentTarget.style.display = "none")}
            />
          )}
          <span className="absolute bottom-4 left-4 rounded-full bg-marigold px-4 py-2 font-display text-xl font-extrabold text-[#2e2110] shadow-lg">
            ৳{fmtNum(p.price_per_unit)}
            <small className="text-sm font-bold">/{unitLabel(p.unit, lang)}</small>
          </span>
        </div>

        <div className="min-w-0">
          <h1 className="font-display text-3xl font-extrabold text-forest">{p.name}</h1>
          <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span className="inline-flex items-center gap-1 rounded-full bg-mint px-2.5 py-1 font-bold text-forest">
              <MapPin className="h-3 w-3" /> {p.district}
            </span>
            {p.farm?.name && <span>· {p.farm.name}</span>}
          </p>
          {p.description && <p className="mt-4 leading-relaxed text-[#4c5f52]">{p.description}</p>}
          <p className="mt-4 text-sm">
            {t("available")}: <b>{fmtNum(p.quantity)} {unitLabel(p.unit, lang)}</b>
            {p.harvest_date && (
              <>
                {" · "}
                {t("harvestDate")}: <b>{p.harvest_date}</b>
              </>
            )}
          </p>

          <Card className="mt-5 p-4">
            <h2 className="font-display font-bold text-forest">{t("farmerLabel")}</h2>
            <p className="mt-1 flex items-center gap-2 text-sm">
              <b>{p.farmer?.name || p.farmer_name || "—"}</b>
              {p.farmer?.is_verified && (
                <Badge tone="green">
                  <BadgeCheck className="h-3.5 w-3.5" /> {t("farmerVerified")}
                </Badge>
              )}
            </p>
            <p className="text-sm text-muted">{p.farmer?.district || p.district}</p>
          </Card>

          <Card className="mt-4 p-4">
            <h2 className="font-display font-bold text-forest">{t("marketComparison")}</h2>
            {latestMarket ? (
              <p className="mt-2 text-sm">
                {t("marketPrice")}: <b>৳{fmtNum(latestMarket.price_per_unit)}/{unitLabel(latestMarket.unit, lang)}</b>{" "}
                <span className="text-muted">
                  ({latestMarket.market_name || latestMarket.district} · {t("source")}: {latestMarket.source})
                </span>
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted">{t("noPrices")}</p>
            )}
            <p className="mt-3 text-xs text-muted">{t("priceNotice")}</p>
          </Card>

          {user?.role === "buyer" && p.quantity > 0 && (p.farmer_id ?? p.farmer?.id) && (
            <div className="mt-5 flex flex-wrap gap-3">
              <Button size="lg" onClick={() => setOrderOpen(true)}>
                <ShoppingCart className="h-4 w-4" /> {t("orderNow")}
              </Button>
              <Button variant="secondary" size="lg" onClick={() => setOfferOpen(true)}>
                <Handshake className="h-4 w-4" /> {t("makeOffer")}
              </Button>
              <MessageButton
                size="lg"
                otherUserId={(p.farmer_id ?? p.farmer?.id) as number}
                listingId={p.id}
                label={t("messageFarmer")}
              />
            </div>
          )}
          {!user && (
            <div className="mt-5">
              <Link to="/login">
                <Button size="lg">{t("loginToView")}</Button>
              </Link>
            </div>
          )}
        </div>
      </div>
      <OrderModal open={orderOpen} onClose={() => setOrderOpen(false)} product={p} />
      <OfferModal open={offerOpen} onClose={() => setOfferOpen(false)} product={p} />
    </div>
  );
}
