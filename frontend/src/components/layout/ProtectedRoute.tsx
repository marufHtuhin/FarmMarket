import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { Spinner, EmptyState, Button } from "../ui/core";
import type { Role } from "../../services/api";

export function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth();
  const { t } = useLang();
  const location = useLocation();

  if (loading) return <Spinner label={t("loading")} />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) {
    return (
      <EmptyState
        icon={<ShieldAlert className="h-10 w-10 text-marigold" />}
        title={t("forbiddenTitle")}
        hint={t("forbiddenText")}
        action={
          <Button variant="secondary" onClick={() => window.history.back()}>
            {t("back")}
          </Button>
        }
      />
    );
  }
  return <>{children}</>;
}
