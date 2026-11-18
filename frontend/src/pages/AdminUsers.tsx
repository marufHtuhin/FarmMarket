import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Search, Users } from "lucide-react";
import { adminApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Input, Select } from "../components/ui/fields";
import { Badge } from "../components/ui/misc";

const PAGE_SIZE = 20;

export function AdminUsersPage() {
  const { t, fmtDate } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(1);

  const q = useQuery({
    queryKey: ["admin-users", search, role, page],
    queryFn: () =>
      adminApi.users({ search: search || undefined, role: role || undefined, page, page_size: PAGE_SIZE }),
    retry: false,
  });

  const verifyMutation = useMutation({
    mutationFn: ({ id, verified }: { id: number; verified: boolean }) => adminApi.verifyUser(id, verified),
    onSuccess: () => {
      toast(t("userVerified"), "success");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const raw = q.data;
  const users = Array.isArray(raw) ? raw : raw?.items || [];
  const total = Array.isArray(raw) ? raw.length : raw?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <PageHeader title={t("usersTitle")} sub={t("adminSub")} />
      <div className="mb-5 grid gap-3 sm:grid-cols-[1fr_180px]">
        <div className="relative min-w-0">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder={t("searchUsers")}
            aria-label={t("searchUsers")}
            className="pl-10"
          />
        </div>
        <Select
          value={role}
          onChange={(e) => {
            setRole(e.target.value);
            setPage(1);
          }}
          aria-label={t("filterRole")}
        >
          <option value="">{t("filterRole")}: {t("all")}</option>
          <option value="farmer">{t("roleFarmer")}</option>
          <option value="buyer">{t("roleBuyer")}</option>
          <option value="transporter">{t("roleTransporter")}</option>
          <option value="admin">{t("roleAdmin")}</option>
        </Select>
      </div>
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && users.length === 0 && (
        <EmptyState icon={<Users className="h-10 w-10 text-leaf" />} title={t("noResults")} />
      )}
      {q.isSuccess && users.length > 0 && (
        <>
          <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-card">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead>
                  <tr className="border-b border-line bg-cream text-xs uppercase tracking-wide text-muted">
                    <th className="px-4 py-3">{t("fullName")}</th>
                    <th className="px-4 py-3">{t("email")}</th>
                    <th className="px-4 py-3">{t("selectRole")}</th>
                    <th className="px-4 py-3">{t("districtLabel")}</th>
                    <th className="px-4 py-3">{t("verifiedBadge")}</th>
                    <th className="px-4 py-3">{t("memberSince")}</th>
                    <th className="px-4 py-3 text-right">{t("edit")}</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-b border-line last:border-0">
                      <td className="px-4 py-3 font-bold">{u.name}</td>
                      <td className="px-4 py-3 text-muted">{u.email}</td>
                      <td className="px-4 py-3 capitalize">{u.role}</td>
                      <td className="px-4 py-3">{u.district || "—"}</td>
                      <td className="px-4 py-3">
                        {u.is_verified ? (
                          <Badge tone="green">
                            <BadgeCheck className="h-3.5 w-3.5" /> {t("verifiedBadge")}
                          </Badge>
                        ) : (
                          <Badge tone="gray">{t("notVerified")}</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted">{u.created_at ? fmtDate(u.created_at) : "—"}</td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={verifyMutation.isPending}
                          onClick={() => verifyMutation.mutate({ id: u.id, verified: !u.is_verified })}
                        >
                          {u.is_verified ? t("unverifyUser") : t("verifyUser")}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-3">
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
