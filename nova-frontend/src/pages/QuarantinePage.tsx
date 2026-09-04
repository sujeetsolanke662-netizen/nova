import { Archive, RefreshCw, ShieldCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { QuarantineTable } from '@/components/quarantine/QuarantineTable'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useQuarantineList } from '@/hooks/useNovaApi'
import { useQuarantineMutation, useQuarantineRestoreMutation } from '@/hooks/useQuarantineActions'

export function QuarantinePage() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuarantineList()
  const quarantine = useQuarantineMutation()
  const restore = useQuarantineRestoreMutation()

  const [path, setPath] = useState('')
  const [reason, setReason] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmedPath = path.trim()
    const trimmedReason = reason.trim()
    if (!trimmedPath || !trimmedReason) return
    quarantine.mutate(
      { path: trimmedPath, reason: trimmedReason },
      {
        onSuccess: () => {
          setPath('')
          setReason('')
        },
      },
    )
  }

  return (
    <div>
      <PageHeader
        title="Quarantine"
        description="A secure holding area for files pulled out of place — nothing here is ever deleted."
        actions={
          <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? 'size-3.5 animate-spin' : 'size-3.5'} />
            Refresh
          </Button>
        }
      />

      <div className="mb-4 flex items-start gap-3 rounded-lg border-l-4 border-ok bg-ok-faint px-4 py-3.5">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-ok" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold tracking-wide text-ok">PROTECTED FROM PERMANENT DELETION</p>
          <p className="mt-0.5 text-sm text-ok">
            Quarantine only relocates a file into NOVA's holding directory and records the move — nothing here is
            ever deleted. Restore brings it straight back to where it came from.
          </p>
        </div>
      </div>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Quarantine a path</CardTitle>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit} className="flex flex-col gap-2.5 sm:flex-row">
            <Input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="C:\Users\me\Downloads\installer.exe"
              className="flex-1 font-mono"
              aria-label="Path to quarantine"
            />
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason…"
              className="flex-1"
              aria-label="Reason for quarantine"
            />
            <Button type="submit" disabled={quarantine.isPending || !path.trim() || !reason.trim()}>
              {quarantine.isPending ? 'Quarantining…' : 'Quarantine'}
            </Button>
          </form>
          {quarantine.isError && (
            <p className="mt-2 text-xs text-danger">
              {quarantine.error instanceof Error ? quarantine.error.message : 'Failed to quarantine this path.'}
            </p>
          )}
        </CardBody>
      </Card>

      <div className="rounded-lg border border-border p-4">
        {isPending && <LoadingState label="Loading quarantined files…" />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : 'Failed to load quarantine list.'}
            onRetry={() => refetch()}
          />
        )}
        {!isPending && !isError && data && data.length === 0 && (
          <EmptyState
            icon={Archive}
            title="Quarantine is clear"
            description="Nothing is currently being held for recovery."
          />
        )}
        {!isPending && !isError && data && data.length > 0 && (
          <>
            <p className="mb-3 text-xs text-ink-muted">
              {data.length} file{data.length === 1 ? '' : 's'} currently held
            </p>
            <QuarantineTable
              entries={data}
              onRestore={(id) => restore.mutate(id)}
              pendingId={restore.isPending ? (restore.variables ?? null) : null}
            />
          </>
        )}
        {restore.isError && (
          <p className="mt-3 text-xs text-danger">
            {restore.error instanceof Error ? restore.error.message : 'Failed to restore this file.'}
          </p>
        )}
      </div>
    </div>
  )
}
