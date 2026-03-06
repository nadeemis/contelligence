import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import { lazy, Suspense } from "react";

// Lazy-load pages for code splitting
const DashboardPage = lazy(() => import("@/pages/Index"));
const ChatPage = lazy(() => import("@/pages/Chat"));
const SessionsPage = lazy(() => import("@/pages/Sessions"));
const SessionDetailPage = lazy(() => import("@/pages/SessionDetailPage"));
const SchedulesPage = lazy(() => import("@/pages/Schedules"));
const ScheduleFormPage = lazy(() => import("@/pages/ScheduleFormPage"));
const ScheduleDetailPage = lazy(() => import("@/pages/ScheduleDetailPage"));
const OutputsPage = lazy(() => import("@/pages/Outputs"));
const MetricsPage = lazy(() => import("@/pages/Metrics"));
const SettingsPage = lazy(() => import("@/pages/Settings"));
const AgentsPage = lazy(() => import("@/pages/Agents"));
const AgentEditorPage = lazy(() => import("@/pages/AgentEditorPage"));
const SkillsPage = lazy(() => import("@/pages/Skills"));
const SkillEditorPage = lazy(() => import("@/pages/SkillEditorPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFound"));

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      console.error("[API] Query failed:", error);
      toast.error(error.message || "An API request failed");
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 5000,
      retry: 2,
      refetchOnWindowFocus: true,
    },
  },
});

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/chat/:sessionId" element={<ChatPage />} />
              <Route path="/sessions" element={<SessionsPage />} />
              <Route path="/sessions/:id" element={<SessionDetailPage />} />
              <Route path="/schedules" element={<SchedulesPage />} />
              <Route path="/schedules/new" element={<ScheduleFormPage />} />
              <Route path="/schedules/:id" element={<ScheduleDetailPage />} />
              <Route path="/schedules/:id/edit" element={<ScheduleFormPage />} />
              <Route path="/outputs" element={<OutputsPage />} />
              <Route path="/metrics" element={<MetricsPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/agents/new" element={<AgentEditorPage />} />
              <Route path="/agents/:agentId" element={<AgentEditorPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/skills/new" element={<SkillEditorPage />} />
              <Route path="/skills/:skillId" element={<SkillEditorPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;