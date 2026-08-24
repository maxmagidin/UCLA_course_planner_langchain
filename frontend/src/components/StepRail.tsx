import { Check, FileSearch, GraduationCap, ListChecks, Sparkles } from 'lucide-react'

import { cn } from '@/lib/utils'

const steps = [
  { label: 'DARS', detail: 'Upload or paste your audit', icon: FileSearch },
  { label: 'Student', detail: 'Review your information', icon: GraduationCap },
  { label: 'Plan', detail: 'Choose quarter or year', icon: ListChecks },
  { label: 'Results', detail: 'Compare schedules', icon: Sparkles },
]

interface StepRailProps {
  current: number
  highest: number
  onNavigate: (step: number) => void
}

export function StepRail({ current, highest, onNavigate }: StepRailProps) {
  return (
    <nav aria-label="Planner progress" className="grid grid-cols-4 gap-1 border-b border-slate-200 bg-white px-3 py-3 lg:sticky lg:top-6 lg:block lg:self-start lg:rounded-2xl lg:border lg:p-3 lg:shadow-sm">
      {steps.map((step, index) => {
        const Icon = step.icon
        const complete = index < current
        const available = index <= highest
        return (
          <button
            key={step.label}
            type="button"
            disabled={!available}
            onClick={() => onNavigate(index)}
            aria-current={current === index ? 'step' : undefined}
            className={cn(
              'group flex min-w-0 flex-col items-center gap-2 rounded-xl px-2 py-3 text-center transition lg:flex-row lg:items-start lg:gap-3 lg:px-3 lg:text-left',
              current === index && 'bg-ucla-blue-soft text-ucla-blue-dark',
              current !== index && available && 'text-slate-500 hover:bg-slate-50 hover:text-slate-900',
              !available && 'cursor-not-allowed text-slate-300',
            )}
          >
            <span className={cn(
              'grid size-8 shrink-0 place-items-center rounded-full border text-xs font-black',
              complete && 'border-emerald-600 bg-emerald-600 text-white',
              current === index && 'border-ucla-blue bg-ucla-blue text-white',
              !complete && current !== index && 'border-slate-200 bg-white',
            )}>
              {complete ? <Check className="size-4" /> : <Icon className="size-4" />}
            </span>
            <span className="min-w-0">
              <strong className="block truncate text-xs font-extrabold lg:text-sm">{step.label}</strong>
              <small className="hidden text-xs leading-5 text-slate-500 lg:block">{step.detail}</small>
            </span>
          </button>
        )
      })}
    </nav>
  )
}
