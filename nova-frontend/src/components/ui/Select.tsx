import type { SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'rounded-md border border-border bg-raised px-3 py-2 text-sm text-ink',
        'focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20',
        className,
      )}
      {...props}
    />
  )
}
