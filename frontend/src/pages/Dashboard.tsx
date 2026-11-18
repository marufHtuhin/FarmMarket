import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Package, ShoppingBasket, TrendingUp, ClipboardList, PlusCircle, Store, Truck, Car, AlertTriangle } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { dashboardApi, demandsApi, deliveriesApi, ordersApi, productsApi, vehiclesApi } from "../services/api";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, PageHeader, Spinner } from "../components/ui/core";
import { Modal, StatusBadge, StatCard } from "../components/ui/misc";
import { Field, Input, Select, Textarea } from "../components/ui/fields";

function DemandModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [form, setForm] = useState({
    product_name: "",
    required_quantity: 1,
    unit: "kg",
    target_price: 0,
    district: "",
    required_date: "",
    notes: "",
  });
  const mutation = useMutation({
    mutationFn: () =>
      demandsApi.create({
        ...form,
        required_date: form.required_date || null,
      }),
    onSuccess: () => {
      toast(t("demandPublishedMsg"), "success");
      qc.invalidateQueries({ queryKey: ["demands"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });
  const set = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));
  const valid = form.product_name.trim() && form.required_quantity > 0 && form.target_price > 0 && form.district.trim();
  return (
    <Modal open={open} onClose={onClose} title={t("postDemand")}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) mutation.mutate();
        }}
      >
        <Field label={t("productName")} required>
          <Input value={form.product_name} onChange={(e) => set("product_name", e.target.value)} required />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("quantity")} required>
            <Input type="number" min={0.1} step={0.1} value={form.required_quantity} onChange={(e) => set("required_quantity", Number(e.target.value))} required />
          </Field>
          <Field label={t("unit")} required>
            <Select value={form.unit} onChange={(e) => set("unit", e.target.value)}>
              <option value="kg">kg</option>
              <option value="quintal">quintal</option>
              <option value="ton">ton</option>
              <option value="piece">piece</option>
            </Select>
          </Field>
          <Field label={t("maxPrice")} required>
            <Input type="number" min={0.01} step={0.01} value={form.target_price} onChange={(e) => set("target_price", Number(e.target.value))} required />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("district")} required>
            <Input value={form.district} onChange={(e) => set("district", e.target.value)} required />
          </Field>
          <Field label={t("harvestDate")}>
            <Input type="date" value={form.required_date} onChange={(e) => set("required_date", e.target.value)} />
          </Field>
        </div>
        <Field label={t("notes")}>
          <Textarea rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button type="submit" loading={mutation.isPending} disabled={!valid}>
            {t("publishDemand")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function FarmerDashboard() {
  const { t, fmtNum } = useLang();
  const { user } = useAuth();
  const dashQ = useQuery({ queryKey: ["dashboard"], queryFn: dashboardApi.get });
  const ordersQ = useQuery({ queryKey: ["orders"], queryFn: ordersApi.listMine });
  const productsQ = useQuery({ queryKey: ["products"], queryFn: () => productsApi.list() });

  const d = dashQ.data;
  const myProducts = (productsQ.data || []).filter((p) => p.farmer_id === user?.id);
  const lowStock = myProducts.filter((p) => p.quantity > 0 && p.quantity <= 5);
  const recent = (ordersQ.data || []).slice(0, 5);

  return (
    <div>
      <PageHeader title={`${t("welcomePrefix")}${user?.name || ""}`} sub={t("dashboardFarmerSub")} action={<Link to="/listings/new"><Button><PlusCircle className="h-4 w-4" /> {t("addProduct")}</Button></Link>} />
      {dashQ.isLoading ? (
        <Spinner label={t("loading")} />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label={t("products")} value={fmtNum(d?.total_products, 0)} icon={<ShoppingBasket className="h-5 w-5" />} />
          <StatCard label={t("stock")} value={fmtNum(d?.available_quantity, 0)} icon={<TrendingUp className="h-5 w-5" />} tint="bg-sand" />
          <StatCard label={t("activeOrders")} value={fmtNum(d?.active_orders, 0)} icon={<Package className="h-5 w-5" />} tint="bg-[#e6f4f1]" />
          <StatCard label={t("sales")} value={`৳${fmtNum(d?.total_sales)}`} icon={<span>৳</span>} tint="bg-[#f2f8e3]" />
        </div>
      )}
      {lowStock.length > 0 && (
        <div className="mt-5 rounded-3xl border border-[#f4e4bf] bg-[#fff8e9] px-5 py-4 text-sm text-[#80632d]">
          <p className="flex items-center gap-2 font-bold">
            <AlertTriangle className="h-4 w-4" /> {t("lowStockHint")}
          </p>
          <p className="mt-1">
            {lowStock.map((p) => `${p.name} (${fmtNum(p.quantity)} ${p.unit})`).join(" · ")}
          </p>
        </div>
      )}
      <Card className="mt-6 p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-extrabold text-forest">{t("recentOrders")}</h2>
          <Link to="/orders" className="text-sm font-bold text-leaf hover:underline">
            {t("viewAll")}
          </Link>
        </div>
        {ordersQ.isLoading ? (
          <Spinner />
        ) : recent.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{t("noOrders")}</p>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {recent.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <Link to={`/orders/${o.id}`} className="min-w-0 font-bold hover:text-leaf">
                  #{o.id} · {o.product_name}
                </Link>
                <span className="flex shrink-0 items-center gap-3">
                  <b>৳{fmtNum(o.total_amount)}</b>
                  <StatusBadge status={o.status} label={t(o.status)} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function BuyerDashboard() {
  const { t, fmtNum } = useLang();
  const { user } = useAuth();
  const [demandOpen, setDemandOpen] = useState(false);
  const dashQ = useQuery({ queryKey: ["dashboard"], queryFn: dashboardApi.get });
  const ordersQ = useQuery({ queryKey: ["orders"], queryFn: ordersApi.listMine });
  const demandsQ = useQuery({ queryKey: ["demands"], queryFn: demandsApi.list });

  const d = dashQ.data;
  const recent = (ordersQ.data || []).slice(0, 5);
  const demands = demandsQ.data || [];

  return (
    <div>
      <PageHeader
        title={`${t("welcomePrefix")}${user?.name || ""}`}
        sub={t("dashboardBuyerSub")}
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setDemandOpen(true)}>
              <ClipboardList className="h-4 w-4" /> {t("postDemand")}
            </Button>
            <Link to="/marketplace">
              <Button>
                <Store className="h-4 w-4" /> {t("navMarket")}
              </Button>
            </Link>
          </div>
        }
      />
      {dashQ.isLoading ? (
        <Spinner label={t("loading")} />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label={t("orders")} value={fmtNum(d?.total_orders, 0)} icon={<Package className="h-5 w-5" />} />
          <StatCard label={t("openDemands")} value={fmtNum(d?.open_demands, 0)} icon={<ClipboardList className="h-5 w-5" />} tint="bg-sand" />
          <StatCard label={t("spent")} value={`৳${fmtNum(d?.total_spent)}`} icon={<span>৳</span>} tint="bg-[#e6f4f1]" />
          <StatCard label={t("recentOrders")} value={fmtNum(d?.recent_orders, 0)} icon={<TrendingUp className="h-5 w-5" />} tint="bg-[#f2f8e3]" />
        </div>
      )}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-extrabold text-forest">{t("recentOrders")}</h2>
            <Link to="/orders" className="text-sm font-bold text-leaf hover:underline">
              {t("viewAll")}
            </Link>
          </div>
          {recent.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{t("noOrders")}</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {recent.map((o) => (
                <li key={o.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                  <Link to={`/orders/${o.id}`} className="min-w-0 font-bold hover:text-leaf">
                    #{o.id} · {o.product_name}
                  </Link>
                  <span className="flex shrink-0 items-center gap-3">
                    <b>৳{fmtNum(o.total_amount)}</b>
                    <StatusBadge status={o.status} label={t(o.status)} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="font-display text-lg font-extrabold text-forest">{t("myDemands")}</h2>
          {demands.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{t("noDemands")}</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {demands.slice(0, 5).map((dm) => (
                <li key={dm.id} className="py-3 text-sm">
                  <b>{dm.product_name}</b>
                  <span className="text-muted">
                    {" "}
                    · {fmtNum(dm.required_quantity)} {dm.unit} · ৳{fmtNum(dm.target_price)}/{dm.unit} · {dm.district}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <DemandModal open={demandOpen} onClose={() => setDemandOpen(false)} />
    </div>
  );
}

function TransporterDashboard() {
  const { t, fmtNum } = useLang();
  const { user } = useAuth();
  const deliveriesQ = useQuery({ queryKey: ["deliveries"], queryFn: deliveriesApi.list, retry: false });
  const vehiclesQ = useQuery({ queryKey: ["vehicles"], queryFn: vehiclesApi.list, retry: false });
  const deliveries = deliveriesQ.data || [];
  const active = deliveries.filter((d) => ["assigned", "picked_up", "in_transit"].includes(d.delivery_status));

  return (
    <div>
      <PageHeader
        title={`${t("welcomePrefix")}${user?.name || ""}`}
        sub={t("dashboardTransporterSub")}
        action={
          <Link to="/vehicles">
            <Button>
              <Car className="h-4 w-4" /> {t("addVehicle")}
            </Button>
          </Link>
        }
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label={t("activeDeliveries")} value={fmtNum(active.length, 0)} icon={<Truck className="h-5 w-5" />} />
        <StatCard label={t("myVehicles")} value={fmtNum((vehiclesQ.data || []).length, 0)} icon={<Car className="h-5 w-5" />} tint="bg-sand" />
        <StatCard label={t("completed")} value={fmtNum(deliveries.filter((d) => d.delivery_status === "delivered").length, 0)} icon={<Package className="h-5 w-5" />} tint="bg-[#e6f4f1]" />
        <StatCard label={t("deliveriesTitle")} value={fmtNum(deliveries.length, 0)} icon={<ClipboardList className="h-5 w-5" />} tint="bg-[#f2f8e3]" />
      </div>
      <Card className="mt-6 p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-extrabold text-forest">{t("deliveriesTitle")}</h2>
          <Link to="/deliveries" className="text-sm font-bold text-leaf hover:underline">
            {t("viewAll")}
          </Link>
        </div>
        {deliveriesQ.isLoading ? (
          <Spinner />
        ) : deliveries.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{t("noDeliveries")}</p>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {deliveries.slice(0, 5).map((d) => (
              <li key={d.order_id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <b className="min-w-0">
                  #{d.order_id} · {d.product_name || ""}
                </b>
                <StatusBadge status={d.delivery_status} label={d.delivery_status.replace(/_/g, " ")} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export function DashboardPage() {
  const { user, loading } = useAuth();
  const { t } = useLang();
  if (loading) return <Spinner label={t("loading")} />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "admin") return <Navigate to="/admin" replace />;
  if (user.role === "farmer") return <FarmerDashboard />;
  if (user.role === "buyer") return <BuyerDashboard />;
  if (user.role === "transporter") return <TransporterDashboard />;
  return <EmptyState title={t("errorGeneric")} />;
}
