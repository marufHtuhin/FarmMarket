import { useNavigate } from "react-router-dom";
import { useLang } from "../i18n/LanguageContext";
import { Card, PageHeader } from "../components/ui/core";
import { ListingForm } from "../components/ListingForm";

export function ListingNewPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={t("newListing")} sub={t("listProduce")} />
      <Card className="p-5 sm:p-6">
        <ListingForm onDone={() => navigate("/listings/mine")} />
      </Card>
    </div>
  );
}
