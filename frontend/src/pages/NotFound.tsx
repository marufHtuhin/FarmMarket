import { Link } from "react-router-dom";
import { SearchX } from "lucide-react";
import { useLang } from "../i18n/LanguageContext";
import { Button, EmptyState } from "../components/ui/core";

export function NotFoundPage() {
  const { t } = useLang();
  return (
    <div className="py-16">
      <EmptyState
        icon={<SearchX className="h-12 w-12 text-muted" />}
        title={t("notFoundTitle")}
        hint={t("notFoundText")}
        action={
          <Link to="/">
            <Button>{t("goHome")}</Button>
          </Link>
        }
      />
    </div>
  );
}
