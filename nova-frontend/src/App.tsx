import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { AskNovaPage } from '@/pages/AskNovaPage'
import { AuditLogPage } from '@/pages/AuditLogPage'
import { ForecastPage } from '@/pages/ForecastPage'
import { GuardrailsPage } from '@/pages/GuardrailsPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { OverviewPage } from '@/pages/OverviewPage'
import { QuarantinePage } from '@/pages/QuarantinePage'
import { RecommendationsPage } from '@/pages/RecommendationsPage'
import { StorageCleanupPage } from '@/pages/StorageCleanupPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="storage-cleanup" element={<StorageCleanupPage />} />
            <Route path="recommendations" element={<RecommendationsPage />} />
            <Route path="quarantine" element={<QuarantinePage />} />
            <Route path="forecast" element={<ForecastPage />} />
            <Route path="ask-nova" element={<AskNovaPage />} />
            <Route path="guardrails" element={<GuardrailsPage />} />
            <Route path="audit-log" element={<AuditLogPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
