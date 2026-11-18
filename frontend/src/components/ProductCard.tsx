import { useState } from "react";
import { Link } from "react-router-dom";
import { MapPin, ShoppingCart, Handshake, BadgeCheck } from "lucide-react";
import type { Product } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useAuth } from "../contexts/AuthContext";
import { productEmoji, productPhoto } from "../utils/crops";
import { unitLabel } from "../utils/format";
import { Button } from "./ui/core";
import { OrderModal } from "./OrderModal";
import { OfferModal } from "./OfferModal";

export function ProductCard({ product }: { product: Product }) {
  const { t, fmtNum, lang } = useLang();
  const { user } = useAuth();
  const [orderOpen, setOrderOpen] = useState(false);
  const [offerOpen, setOfferOpen] = useState(false);

  const imgSrc =
    product.image_url && /^https?:\/\//i.test(product.image_url)
      ? product.image_url
      : product.images?.[0]?.url || productPhoto(product.name);
  const lowStock = product.quantity > 0 && product.quantity <= 5;

  return (
    <article className="flex flex-col overflow-hidden rounded-3xl border border-line bg-white shadow-card transition hover:-translate-y-1 hover:shadow-lift">
      <Link to={`/marketplace/${product.id}`} className="relative block h-44 shrink-0 overflow-hidden bg-gradient-to-br from-[#e7f3e8] via-[#f6f3e2] to-[#fdf3d7]">
        <span className="absolute inset-0 grid place-items-center text-6xl">{productEmoji(product.name)}</span>
        {imgSrc && (
          <img
            src={imgSrc}
            alt={product.name}
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
        )}
        <span className="absolute bottom-3 left-3 rounded-full bg-marigold px-3.5 py-1.5 font-display text-base font-extrabold text-[#2e2110] shadow-lg">
          ৳{fmtNum(product.price_per_unit)}
          <small className="text-xs font-bold">/{unitLabel(product.unit, lang)}</small>
        </span>
        {lowStock && (
          <span className="absolute right-3 top-3 rounded-full bg-red-600 px-2.5 py-1 text-[11px] font-extrabold text-white shadow">
            {t("lowStock")}
          </span>
        )}
      </Link>
      <div className="flex flex-1 flex-col p-5">
        <Link to={`/marketplace/${product.id}`}>
          <h3 className="font-display text-xl font-extrabold hover:text-leaf">{product.name}</h3>
        </Link>
        <p className="mt-2.5 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="inline-flex items-center gap-1 rounded-full bg-mint px-2.5 py-1 font-bold text-forest">
            <MapPin className="h-3 w-3" /> {product.district}
          </span>
          <span className="inline-flex items-center gap-1 text-muted">
            {product.farmer_name || product.farmer?.name}
            {(product.farmer?.is_verified ?? false) && <BadgeCheck className="h-3.5 w-3.5 text-leaf" />}
          </span>
        </p>
        <p className="my-3 min-h-[38px] text-[13px] leading-relaxed text-[#65736a]">{product.description || ""}</p>
        <p className="text-[13px] text-[#536257]">
          {t("available")}: <b>{fmtNum(product.quantity)} {unitLabel(product.unit, lang)}</b>
        </p>
        {user?.role === "buyer" && product.quantity > 0 && (
          <div className="mt-4 flex gap-2">
            <Button className="flex-1" size="sm" onClick={() => setOrderOpen(true)}>
              <ShoppingCart className="h-4 w-4" /> {t("order")}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setOfferOpen(true)}>
              <Handshake className="h-4 w-4" /> {t("makeOffer")}
            </Button>
          </div>
        )}
      </div>
      <OrderModal open={orderOpen} onClose={() => setOrderOpen(false)} product={product} />
      <OfferModal open={offerOpen} onClose={() => setOfferOpen(false)} product={product} />
    </article>
  );
}
