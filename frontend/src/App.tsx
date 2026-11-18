import { lazy, Suspense } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { PublicLayout } from "./components/layout/PublicLayout";
import { AppLayout } from "./components/layout/AppLayout";
import { ProtectedRoute } from "./components/layout/ProtectedRoute";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Spinner } from "./components/ui/core";
import type { Role } from "./services/api";

// Route-level code splitting: each page is its own chunk, loaded on demand.
// The layouts stay eager (every route needs one). Pages use named exports,
// so each lazy import maps the named export to the default React.lazy expects.
// About.tsx and AdminData.tsx each export two pages; importing the same
// module twice still produces a single shared chunk.
const LandingPage = lazy(() => import("./pages/Landing").then((m) => ({ default: m.LandingPage })));
const AboutPage = lazy(() => import("./pages/About").then((m) => ({ default: m.AboutPage })));
const HowItWorksPage = lazy(() => import("./pages/About").then((m) => ({ default: m.HowItWorksPage })));
const MarketplacePage = lazy(() => import("./pages/Marketplace").then((m) => ({ default: m.MarketplacePage })));
const ProductDetailPage = lazy(() =>
  import("./pages/ProductDetail").then((m) => ({ default: m.ProductDetailPage }))
);
const LoginPage = lazy(() => import("./pages/Login").then((m) => ({ default: m.LoginPage })));
const RegisterPage = lazy(() => import("./pages/Register").then((m) => ({ default: m.RegisterPage })));
const ForgotPasswordPage = lazy(() =>
  import("./pages/ForgotPassword").then((m) => ({ default: m.ForgotPasswordPage }))
);
const ResetPasswordPage = lazy(() =>
  import("./pages/ResetPassword").then((m) => ({ default: m.ResetPasswordPage }))
);
const VerifyEmailPage = lazy(() =>
  import("./pages/VerifyEmail").then((m) => ({ default: m.VerifyEmailPage }))
);
const VerifyPage = lazy(() => import("./pages/Verify").then((m) => ({ default: m.VerifyPage })));
const DashboardPage = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.DashboardPage })));
const FarmsPage = lazy(() => import("./pages/Farms").then((m) => ({ default: m.FarmsPage })));
const ListingNewPage = lazy(() => import("./pages/ListingNew").then((m) => ({ default: m.ListingNewPage })));
const MyListingsPage = lazy(() => import("./pages/MyListings").then((m) => ({ default: m.MyListingsPage })));
const QualityPage = lazy(() => import("./pages/Quality").then((m) => ({ default: m.QualityPage })));
const PricesPage = lazy(() => import("./pages/Prices").then((m) => ({ default: m.PricesPage })));
const WeatherPage = lazy(() => import("./pages/Weather").then((m) => ({ default: m.WeatherPage })));
const MatchesPage = lazy(() => import("./pages/Matches").then((m) => ({ default: m.MatchesPage })));
const OffersPage = lazy(() => import("./pages/Offers").then((m) => ({ default: m.OffersPage })));
const MessagesPage = lazy(() => import("./pages/Messages").then((m) => ({ default: m.MessagesPage })));
const OrdersPage = lazy(() => import("./pages/Orders").then((m) => ({ default: m.OrdersPage })));
const OrderDetailPage = lazy(() => import("./pages/OrderDetail").then((m) => ({ default: m.OrderDetailPage })));
const AssistantPage = lazy(() => import("./pages/Assistant").then((m) => ({ default: m.AssistantPage })));
const LogisticsPage = lazy(() => import("./pages/Logistics").then((m) => ({ default: m.LogisticsPage })));
const BatchesPage = lazy(() => import("./pages/Batches").then((m) => ({ default: m.BatchesPage })));
const BatchDetailPage = lazy(() => import("./pages/BatchDetail").then((m) => ({ default: m.BatchDetailPage })));
const DeliveriesPage = lazy(() => import("./pages/Deliveries").then((m) => ({ default: m.DeliveriesPage })));
const VehiclesPage = lazy(() => import("./pages/Vehicles").then((m) => ({ default: m.VehiclesPage })));
const AdminDashboardPage = lazy(() =>
  import("./pages/AdminDashboard").then((m) => ({ default: m.AdminDashboardPage }))
);
const AdminUsersPage = lazy(() => import("./pages/AdminUsers").then((m) => ({ default: m.AdminUsersPage })));
const AdminDataSourcesPage = lazy(() =>
  import("./pages/AdminData").then((m) => ({ default: m.AdminDataSourcesPage }))
);
const AdminAuditLogsPage = lazy(() =>
  import("./pages/AdminData").then((m) => ({ default: m.AdminAuditLogsPage }))
);
const NotificationsPage = lazy(() =>
  import("./pages/Notifications").then((m) => ({ default: m.NotificationsPage }))
);
const ProfilePage = lazy(() => import("./pages/Profile").then((m) => ({ default: m.ProfilePage })));
const NotFoundPage = lazy(() => import("./pages/NotFound").then((m) => ({ default: m.NotFoundPage })));

function P({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  return <ProtectedRoute roles={roles}>{children}</ProtectedRoute>;
}

function PageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner />
    </div>
  );
}

export default function App() {
  const location = useLocation();
  return (
    // ErrorBoundary sits outside Suspense so it also catches failed lazy
    // chunk loads; resetKey recovers the app when the user navigates away
    // from a crashed page.
    <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public layout — no sidebar */}
          <Route element={<PublicLayout />}>
            <Route path="/" element={<LandingPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/how-it-works" element={<HowItWorksPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/verify" element={<VerifyPage />} />
            <Route path="/verify/:code" element={<VerifyPage />} />
          </Route>

          {/* App layout — sidebar + bottom nav */}
          <Route element={<AppLayout />}>
            <Route path="/marketplace" element={<MarketplacePage />} />
            <Route path="/marketplace/:id" element={<ProductDetailPage />} />
            <Route path="/prices" element={<PricesPage />} />
            <Route path="/weather" element={<WeatherPage />} />
            <Route path="/dashboard" element={<P><DashboardPage /></P>} />
            <Route path="/farms" element={<P roles={["farmer"]}><FarmsPage /></P>} />
            <Route path="/listings/new" element={<P roles={["farmer"]}><ListingNewPage /></P>} />
            <Route path="/listings/mine" element={<P roles={["farmer"]}><MyListingsPage /></P>} />
            <Route path="/quality" element={<P roles={["farmer"]}><QualityPage /></P>} />
            <Route path="/matches" element={<P><MatchesPage /></P>} />
            <Route path="/offers" element={<P roles={["farmer", "buyer"]}><OffersPage /></P>} />
            <Route path="/messages" element={<P roles={["farmer", "buyer"]}><MessagesPage /></P>} />
            <Route path="/messages/:id" element={<P roles={["farmer", "buyer"]}><MessagesPage /></P>} />
            <Route path="/orders" element={<P><OrdersPage /></P>} />
            <Route path="/orders/:id" element={<P><OrderDetailPage /></P>} />
            <Route path="/assistant" element={<P><AssistantPage /></P>} />
            <Route path="/logistics" element={<P><LogisticsPage /></P>} />
            <Route path="/batches" element={<P roles={["farmer"]}><BatchesPage /></P>} />
            <Route path="/batches/:code" element={<P roles={["farmer"]}><BatchDetailPage /></P>} />
            <Route path="/deliveries" element={<P roles={["transporter"]}><DeliveriesPage /></P>} />
            <Route path="/vehicles" element={<P roles={["transporter"]}><VehiclesPage /></P>} />
            <Route path="/admin" element={<P roles={["admin"]}><AdminDashboardPage /></P>} />
            <Route path="/admin/users" element={<P roles={["admin"]}><AdminUsersPage /></P>} />
            <Route path="/admin/data-sources" element={<P roles={["admin"]}><AdminDataSourcesPage /></P>} />
            <Route path="/admin/audit-logs" element={<P roles={["admin"]}><AdminAuditLogsPage /></P>} />
            <Route path="/notifications" element={<P><NotificationsPage /></P>} />
            <Route path="/profile" element={<P><ProfilePage /></P>} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
