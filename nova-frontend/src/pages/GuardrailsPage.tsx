import { Search, ShieldCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { ClassificationResult } from '@/components/guardrails/ClassificationResult'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorState } from '@/components/ui/StateViews'
import { useGuardrailsCheck } from '@/hooks/useGuardrailsCheck'

const EXAMPLE_PATHS = ['/etc/passwd', '/home/user/Downloads/installer.deb', '/var/log/syslog']

export function GuardrailsPage() {
  const [path, setPath] = useState('')
  const { mutate, data, isPending, isError, error, reset } = useGuardrailsCheck()

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = path.trim()
    if (!trimmed) return
    mutate(trimmed)
  }

  function handleExample(example: string) {
    setPath(example)
    mutate(example)
  }

  return (
    <div>
      <PageHeader
        title="Guardrails"
        description="NOVA's safety gate, read-only — check whether a path is blocked, out of scope, or allowed before anything would ever act on it."
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-ink-dim" />
            Path classifier
          </CardTitle>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit} className="flex flex-col gap-2.5 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" />
              <Input
                value={path}
                onChange={(e) => {
                  setPath(e.target.value)
                  if (data || isError) reset()
                }}
                placeholder="/home/user/Downloads/example.tar.gz"
                className="w-full pl-9 font-mono"
                aria-label="Path to check"
              />
            </div>
            <Button type="submit" disabled={isPending || !path.trim()}>
              {isPending ? 'Checking…' : 'Check path'}
            </Button>
          </form>

          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>Try:</span>
            {EXAMPLE_PATHS.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => handleExample(example)}
                className="rounded-md bg-raised px-2 py-1 font-mono text-ink-muted hover:bg-border-faint hover:text-ink"
              >
                {example}
              </button>
            ))}
          </div>

          <div className="mt-4">
            {isError && (
              <ErrorState
                message={error instanceof Error ? error.message : 'Failed to check this path.'}
              />
            )}
            {data && <ClassificationResult result={data} />}
          </div>
        </CardBody>
      </Card>
    </div>
  )
}
