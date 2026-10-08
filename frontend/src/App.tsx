import React, { useState } from "react";
import { AppProvider } from "./context/AppContext";
import { Layout } from "./components/Layout";
import type { TabId } from "./components/Layout";
import { OverviewPage } from "./pages/OverviewPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { LayaWorkspacePage } from "./pages/LayaWorkspacePage";
import { MemoryExplorerPage } from "./pages/MemoryExplorerPage";
import { RulesIntelligencePage } from "./pages/RulesIntelligencePage";
import { SecurityTrustPage } from "./pages/SecurityTrustPage";
import { GitRecoveryPage } from "./pages/GitRecoveryPage";
import { SessionsPage } from "./pages/SessionsPage";
import { ActivityPage } from "./pages/ActivityPage";

export const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  return (
    <Layout activeTab={activeTab} onTabChange={setActiveTab}>
      {activeTab === "overview" && <OverviewPage onNavigate={setActiveTab} />}
      {activeTab === "providers" && <ProvidersPage />}
      {activeTab === "laya" && <LayaWorkspacePage />}
      {activeTab === "memory" && <MemoryExplorerPage />}
      {activeTab === "rules" && <RulesIntelligencePage />}
      {activeTab === "security" && <SecurityTrustPage />}
      {activeTab === "git" && <GitRecoveryPage />}
      {activeTab === "sessions" && <SessionsPage />}
      {activeTab === "activity" && <ActivityPage />}
    </Layout>
  );
};

export default function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}
