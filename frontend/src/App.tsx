import { useState } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useParams } from "react-router-dom";
import { Sidebar } from "./components/Layout/Sidebar";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { FinancialPanel } from "./components/FinancialPanel/FinancialPanel";
import { GenerationControls } from "./components/GenerationControls/GenerationControls";
import { Iso20022Panel } from "./components/Iso20022Panel/Iso20022Panel";
import { ResultsViewer } from "./components/ResultsViewer/ResultsViewer";
import { TemplateLibrary } from "./components/TemplateLibrary/TemplateLibrary";
import { ToastContainer } from "./components/Toast/Toast";
import { ToastProvider, useToast } from "./hooks/useToast";

function ResultsViewerWrapper() {
  const { id } = useParams();
  return <ResultsViewer preselectedDatasetId={id} />;
}

function AppRoutes() {
  const navigate = useNavigate();
  const { toasts, removeToast } = useToast();
  const [pendingTemplate, setPendingTemplate] = useState<string | null>(null);

  const handleApply = (name: string) => {
    setPendingTemplate(name);
    navigate("/generation");
  };

  const handleNavigate = (page: string) => {
    const map: Record<string, string> = {
      dashboard: "/",
      templates: "/templates",
      iso20022: "/iso20022",
      financial: "/financial",
      generation: "/generation",
      datasets: "/datasets",
    };
    navigate(map[page] || page);
  };

  return (
    <div className="flex h-screen bg-[var(--bg)] text-[var(--text)]">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/templates" element={<TemplateLibrary onApply={handleApply} />} />
          <Route path="/iso20022" element={<Iso20022Panel onApply={handleApply} />} />
          <Route path="/financial" element={<FinancialPanel onNavigate={handleNavigate} />} />
          <Route path="/generation" element={<GenerationControls onNavigate={handleNavigate} pendingTemplate={pendingTemplate} />} />
          <Route path="/datasets" element={<ResultsViewer />} />
          <Route path="/datasets/:id" element={<ResultsViewerWrapper />} />
        </Routes>
      </main>
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </BrowserRouter>
  );
}

export default App;
