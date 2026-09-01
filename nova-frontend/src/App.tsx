import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { AuditLogPage } from '@/pages/AuditLogPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { GuardrailsPage } from '@/pages/GuardrailsPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
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
            <Route index element={<DashboardPage />} />
            <Route path="storage-cleanup" element={<StorageCleanupPage />} />
            <Route path="guardrails" element={<GuardrailsPage />} />
            <Route path="audit-log" element={<AuditLogPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
