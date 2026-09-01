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
        description="Read-only inspection of NOVA's safety gate — check whether a path is protected, in scan scope, or reviewable before NOVA would ever act on it."
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-brand-600 dark:text-brand-400" />
            Check a path
          </CardTitle>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
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

          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span>Try:</span>
            {EXAMPLE_PATHS.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => handleExample(example)}
                className="rounded-md bg-slate-100 px-2 py-1 font-mono text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {example}
              </button>
            ))}
          </div>

          <div className="mt-5">
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
