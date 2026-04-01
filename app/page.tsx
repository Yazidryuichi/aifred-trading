import { ErrorBoundary } from "@/components/ErrorBoundary";
import { TradingDashboardLoader } from "@/components/trading/TradingDashboardLoader";

export default function HomePage() {
  return (
    <ErrorBoundary>
      <TradingDashboardLoader />
    </ErrorBoundary>
  );
}
