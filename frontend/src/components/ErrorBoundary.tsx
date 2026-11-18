import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "./ui/core";
import { useLang } from "../i18n/LanguageContext";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** When this value changes while an error is shown, the boundary resets.
   *  App passes the current route, so navigating away from a crashed page
   *  recovers the app instead of leaving the fallback stuck on screen. */
  resetKey?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/** Friendly fallback for a crashed page. A function component so it can use
 *  the app's i18n; the boundary itself must be a class component because
 *  React only exposes getDerivedStateFromError / componentDidCatch on classes.
 *  Uses the existing errorTitle / errorGeneric / retry dictionary keys. */
function ErrorFallback({ error, onRetry }: { error: Error | null; onRetry: () => void }) {
  const { t } = useLang();
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      <AlertTriangle className="h-10 w-10 text-marigold" />
      <h1 className="font-display text-2xl font-extrabold text-forest">{t("errorTitle")}</h1>
      <p className="max-w-md text-sm leading-relaxed text-muted">{t("errorGeneric")}</p>
      {import.meta.env.DEV && error && (
        <details className="max-w-md text-left text-xs text-muted">
          <summary className="cursor-pointer font-bold">Error details (dev only)</summary>
          <pre className="mt-2 whitespace-pre-wrap break-words rounded-xl bg-white/70 p-3">{error.message}</pre>
        </details>
      )}
      <Button onClick={onRetry} className="mt-2">
        {t("retry")}
      </Button>
    </div>
  );
}

/** Catches render errors (including failed lazy chunk loads) anywhere below
 *  it so a crash in one page never whitescreens the whole app. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Visible in the browser console for debugging; never sent anywhere.
    console.error("FarmMarket error boundary caught:", error, info);
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null });
    }
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return <ErrorFallback error={this.state.error} onRetry={this.handleRetry} />;
    }
    return this.props.children;
  }
}
