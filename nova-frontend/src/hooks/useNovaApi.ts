import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    // Backend health is cheap to poll and drives the sidebar status dot.
    refetchInterval: 15_000,
    retry: 1,
  })
}

export function useAptClutterScan() {
  return useQuery({
    queryKey: ['apt-clutter-scan'],
    queryFn: api.aptClutterScan,
    staleTime: 30_000,
  })
}

export function useAuditLog() {
  return useQuery({
    queryKey: ['audit-log'],
    queryFn: api.auditLog,
    staleTime: 15_000,
  })
}

export function useAuditLogVerify() {
  return useQuery({
    queryKey: ['audit-log-verify'],
    queryFn: api.auditLogVerify,
    staleTime: 15_000,
  })
}

export function useQuarantineList() {
  return useQuery({
    queryKey: ['quarantine'],
    queryFn: api.quarantineList,
    staleTime: 10_000,
  })
}
