import { FileText, Sparkles } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardBody } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorState } from '@/components/ui/StateViews'
import { useCopilotAsk } from '@/hooks/useCopilotAsk'
import { truncatePath } from '@/lib/format'
import { getTrackedLocation } from '@/lib/trackedLocation'

const EXAMPLE_QUESTIONS = [
  "What's using up my space?",
  'What can I safely delete?',
  'Do I have any duplicate files?',
]

const INTENT_LABELS: Record<string, string> = {
  why_full: 'Space usage',
  find_duplicates: 'Duplicate search',
  whats_safe: 'Safety review',
  general: 'General query',
}

const SUGGESTED_NEXT_STEP: Record<string, string> = {
  why_full: 'Review the cited files below, then run Recommendations for a full scored scan.',
  find_duplicates: 'Open Recommendations to quarantine confirmed duplicates.',
  whats_safe: 'Files marked auto-apply in Recommendations can be quarantined directly.',
  general: 'Run a Recommendations scan for a structured, scored view of this directory.',
}

export function AskNovaPage() {
  const [root, setRoot] = useState(getTrackedLocation)
  const [question, setQuestion] = useState('')
  const { mutate: ask, data, isPending, isError, error, reset } = useCopilotAsk()

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmedRoot = root.trim()
    const trimmedQuestion = question.trim()
    if (!trimmedRoot || !trimmedQuestion) return
    ask({ question: trimmedQuestion, root: trimmedRoot })
  }

  function handleExample(example: string) {
    setQuestion(example)
    if (data || isError) reset()
  }

  return (
    <div>
      <PageHeader
        title="Ask Nova"
        description="Ask a plain-English question about a scanned directory. Answers are composed entirely from NOVA's own recommendation data — never a language model."
      />

      <Card className="mb-4">
        <CardBody>
          <form onSubmit={handleSubmit} className="flex flex-col gap-2.5">
            <Input
              value={root}
              onChange={(e) => {
                setRoot(e.target.value)
                if (data || isError) reset()
              }}
              placeholder="Root directory, e.g. C:\Users\me\Downloads"
              className="w-full font-mono"
              aria-label="Root directory to search"
            />
            <div className="flex flex-col gap-2.5 sm:flex-row">
              <Input
                value={question}
                onChange={(e) => {
                  setQuestion(e.target.value)
                  if (data || isError) reset()
                }}
                placeholder="What's taking up all my space?"
                className="flex-1"
                aria-label="Question for NOVA Copilot"
              />
              <Button type="submit" disabled={isPending || !root.trim() || !question.trim()}>
                <Sparkles className="size-3.5" />
                {isPending ? 'Analyzing…' : 'Ask'}
              </Button>
            </div>
          </form>

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
            <span>Try:</span>
            {EXAMPLE_QUESTIONS.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => handleExample(example)}
                className="rounded-md bg-raised px-2 py-1 text-ink-muted hover:bg-border-faint hover:text-ink"
              >
                {example}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {isPending && (
        <Card>
          <CardBody>
            <div className="flex items-center gap-2.5 py-2 text-sm text-accent-ink">
              <Sparkles className="size-4 animate-pulse" aria-hidden="true" />
              Searching and composing an answer…
            </div>
          </CardBody>
        </Card>
      )}

      {isError && (
        <Card>
          <CardBody>
            <ErrorState message={error instanceof Error ? error.message : 'Failed to get an answer.'} />
          </CardBody>
        </Card>
      )}

      {data && !isPending && !isError && (
        <div className="flex flex-col gap-3">
          <Card>
            <CardBody>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-accent-ink uppercase">
                <Sparkles className="size-3.5" aria-hidden="true" />
                Nova analysis
                <Badge tone="nova" className="ml-1">
                  {INTENT_LABELS[data.intent] ?? data.intent.replace(/_/g, ' ')}
                </Badge>
              </p>
              <p className="text-sm whitespace-pre-line text-ink">{data.answer_text}</p>
            </CardBody>
          </Card>

          {data.cited_paths.length > 0 && (
            <Card>
              <CardBody>
                <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-muted uppercase">
                  <FileText className="size-3.5" aria-hidden="true" />
                  Evidence — cited paths
                </p>
                <ul className="divide-y divide-border-faint">
                  {data.cited_paths.map((p) => (
                    <li key={p} title={p} className="py-1.5 font-mono text-xs text-ink-muted">
                      {truncatePath(p, 90)}
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardBody className="flex items-start gap-2.5">
              <div className="mt-0.5 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
              <div>
                <p className="text-xs font-semibold tracking-wide text-ink-muted uppercase">Recommended action</p>
                <p className="mt-0.5 text-sm text-ink">
                  {SUGGESTED_NEXT_STEP[data.intent] ?? SUGGESTED_NEXT_STEP.general}
                </p>
              </div>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  )
}
