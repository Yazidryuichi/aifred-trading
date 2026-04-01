import { ErrorBoundary } from "@/components/ErrorBoundary";
import ConfigPanel from "@/components/trading/ConfigPanel";

export default function ConfigPage() {
  return (
    <ErrorBoundary>
      <ConfigPanel />
    </ErrorBoundary>
  );
}
