import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, SearchX } from "lucide-react";
import { productsApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { CATEGORIES, filterProducts, paginate, type CropCategory } from "../utils/crops";
import { apiErrorMessage } from "../utils/format";
import { ProductCard } from "../components/ProductCard";
import { Button, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Input, Select } from "../components/ui/fields";

const PAGE_SIZE = 12;

export function MarketplacePage() {
  const { t } = useLang();
  const [search, setSearch] = useState("");
  const [district, setDistrict] = useState("");
  const [category, setCategory] = useState<CropCategory>("all");
  const [sort, setSort] = useState<"newest" | "price-asc" | "price-desc">("newest");
  const [page, setPage] = useState(1);

  const q = useQuery({ queryKey: ["products"], queryFn: () => productsApi.list() });

  const districts = useMemo(() => {
    const set = new Set((q.data || []).map((p) => p.district).filter(Boolean));
    return [...set].sort();
  }, [q.data]);

  const filtered = useMemo(
    () => filterProducts(q.data || [], { search, district, category, sort }),
    [q.data, search, district, category, sort]
  );
  const { pageItems, totalPages } = useMemo(() => paginate(filtered, page, PAGE_SIZE), [filtered, page]);

  const resetPage = () => setPage(1);

  return (
    <div>
      <PageHeader title={t("freshMarket")} sub={t("marketSub")} />
      <div className="mb-5 space-y-3">
        <div className="grid gap-3 sm:grid-cols-[1fr_180px_180px]">
          <div className="relative min-w-0">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                resetPage();
              }}
              placeholder={t("searchProduct")}
              aria-label={t("searchProduct")}
              className="pl-10"
            />
          </div>
          <Select
            value={district}
            onChange={(e) => {
              setDistrict(e.target.value);
              resetPage();
            }}
            aria-label={t("districtLabel")}
          >
            <option value="">{t("districtLabel")}: {t("all")}</option>
            {districts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
          <Select
            value={sort}
            onChange={(e) => setSort(e.target.value as typeof sort)}
            aria-label={t("sortBy")}
          >
            <option value="newest">{t("sortNewest")}</option>
            <option value="price-asc">{t("sortPriceAsc")}</option>
            <option value="price-desc">{t("sortPriceDesc")}</option>
          </Select>
        </div>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => {
                setCategory(c.key);
                resetPage();
              }}
              aria-pressed={category === c.key}
              className={`rounded-full px-4 py-2 text-sm font-bold shadow-sm transition ${
                category === c.key ? "bg-forest text-white" : "border border-line bg-white text-[#506057] hover:border-leaf hover:text-forest"
              }`}
            >
              {t(c.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && filtered.length === 0 && (
        <EmptyState icon={<SearchX className="h-10 w-10 text-muted" />} title={t("noResults")} hint={t("tryDifferentSearch")} />
      )}
      {q.isSuccess && filtered.length > 0 && (
        <>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {pageItems.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
          {totalPages > 1 && (
            <div className="mt-8 flex items-center justify-center gap-3">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                {t("previous")}
              </Button>
              <span className="text-sm font-bold">
                {t("pageOf")} {page} / {totalPages}
              </span>
              <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
                {t("next")}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
