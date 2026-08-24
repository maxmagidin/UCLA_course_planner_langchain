import { ArrowLeft, CalendarDays, CalendarRange, CircleAlert, Play, SlidersHorizontal } from 'lucide-react'

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, Input, Select, Textarea } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import type { ConstraintsState, EditableTerm, StudentProfile } from '@/types'

const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

interface PlanningStepProps {
  mode: 'quarter' | 'year'
  onModeChange: (mode: 'quarter' | 'year') => void
  academicYear: number
  onAcademicYearChange: (year: number) => void
  includeSummer: boolean
  onIncludeSummerChange: (include: boolean) => void
  terms: EditableTerm[]
  onTermsChange: (terms: EditableTerm[]) => void
  profile: StudentProfile
  onProfileChange: (profile: StudentProfile) => void
  constraints: ConstraintsState
  onConstraintsChange: (constraints: ConstraintsState) => void
  loading: boolean
  error: string
  onBack: () => void
  onRun: () => void
}

export function PlanningStep({
  mode,
  onModeChange,
  academicYear,
  onAcademicYearChange,
  includeSummer,
  onIncludeSummerChange,
  terms,
  onTermsChange,
  profile,
  onProfileChange,
  constraints,
  onConstraintsChange,
  loading,
  error,
  onBack,
  onRun,
}: PlanningStepProps) {
  const updateTerm = (id: string, patch: Partial<EditableTerm>) => {
    onTermsChange(terms.map((term) => term.id === id ? { ...term, ...patch } : term))
  }
  const updateProfile = <K extends keyof StudentProfile>(key: K, value: StudentProfile[K]) => {
    onProfileChange({ ...profile, [key]: value })
  }
  const yearOptions = Array.from({ length: 5 }, (_, index) => new Date().getFullYear() - 1 + index)

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="border-b border-slate-100">
          <Badge variant="gold" className="w-fit">Step 3 · Planning horizon</Badge>
          <CardTitle className="mt-2 text-2xl sm:text-3xl">Plan one quarter or map the academic year</CardTitle>
          <CardDescription className="max-w-3xl">
            Required courses must appear in a valid schedule. Preferred courses are ranked higher when they fit. In year mode, each recommended quarter carries into the next prerequisite check.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-7 pt-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => onModeChange('quarter')}
              className={cn('flex items-start gap-4 rounded-2xl border p-5 text-left transition', mode === 'quarter' ? 'border-ucla-blue bg-ucla-blue-soft ring-2 ring-ucla-blue/10' : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50')}
            >
              <span className={cn('grid size-11 shrink-0 place-items-center rounded-xl', mode === 'quarter' ? 'bg-ucla-blue text-white' : 'bg-slate-100 text-slate-500')}><CalendarDays /></span>
              <span><strong className="block text-base text-slate-950">One quarter</strong><span className="mt-1 block text-sm leading-5 text-slate-500">Build section-level schedules from a published UCLA term.</span></span>
            </button>
            <button
              type="button"
              onClick={() => onModeChange('year')}
              className={cn('flex items-start gap-4 rounded-2xl border p-5 text-left transition', mode === 'year' ? 'border-ucla-blue bg-ucla-blue-soft ring-2 ring-ucla-blue/10' : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50')}
            >
              <span className={cn('grid size-11 shrink-0 place-items-center rounded-xl', mode === 'year' ? 'bg-ucla-blue text-white' : 'bg-slate-100 text-slate-500')}><CalendarRange /></span>
              <span><strong className="block text-base text-slate-950">Academic year</strong><span className="mt-1 block text-sm leading-5 text-slate-500">Sequence Fall, Winter, Spring, and optionally Summer.</span></span>
            </button>
          </div>

          {mode === 'year' && (
            <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:flex-row sm:items-end sm:justify-between">
              <Field label="Academic year begins" className="w-full sm:max-w-56">
                <Select value={academicYear} onChange={(event) => onAcademicYearChange(Number(event.target.value))}>
                  {yearOptions.map((year) => <option key={year} value={year}>{year}–{String(year + 1).slice(-2)}</option>)}
                </Select>
              </Field>
              <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700">
                <input type="checkbox" className="size-4 accent-ucla-blue" checked={includeSummer} onChange={(event) => onIncludeSummerChange(event.target.checked)} />
                Include Summer {academicYear + 1}
              </label>
            </div>
          )}

          <div className={cn('grid gap-4', mode === 'year' && 'xl:grid-cols-2')}>
            {terms.map((term, index) => (
              <div key={term.id} className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50/65 p-5">
                <div className="mb-5 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[.15em] text-ucla-blue">{mode === 'year' ? `Quarter ${index + 1}` : 'Target quarter'}</p>
                    <h3 className="mt-1 text-lg font-extrabold text-slate-950">{term.term || 'Choose a term'}</h3>
                  </div>
                  <Badge variant="outline">{term.minUnits}–{term.maxUnits} units</Badge>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="UCLA term" className="sm:col-span-2">
                    <Input value={term.term} onChange={(event) => updateTerm(term.id, { term: event.target.value })} placeholder="Fall 2026" />
                  </Field>
                  <Field label="Required courses" hint="One per line. Every required course must be offered and fit.">
                    <Textarea className="min-h-32 font-mono text-xs leading-6" value={term.requiredText} onChange={(event) => updateTerm(term.id, { requiredText: event.target.value })} placeholder={'COM SCI 111\nCOM SCI 180'} />
                  </Field>
                  <Field label="Preferred courses" optional hint="Used when they fit the unit and time constraints.">
                    <Textarea className="min-h-32 font-mono text-xs leading-6" value={term.preferredText} onChange={(event) => updateTerm(term.id, { preferredText: event.target.value })} placeholder={'COM SCI 118\nSTATS 100A'} />
                  </Field>
                  <Field label="Minimum units">
                    <Input type="number" min="0" max="30" value={term.minUnits} onChange={(event) => updateTerm(term.id, { minUnits: Number(event.target.value) })} />
                  </Field>
                  <Field label="Maximum units">
                    <Input type="number" min="0" max="30" value={term.maxUnits} onChange={(event) => updateTerm(term.id, { maxUnits: Number(event.target.value) })} />
                  </Field>
                </div>
              </div>
            ))}
          </div>

          {mode === 'year' && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
              <CircleAlert className="mt-0.5 size-5 shrink-0" />
              <p className="leading-6"><strong>Published-term boundary:</strong> section-level results depend on UCLA Schedule of Classes data. A future quarter can remain partial or fail until UCLA publishes it; completed earlier recommendations are still carried forward.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Schedule preferences</CardTitle>
          <CardDescription>These constraints apply to every quarter in this run.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-5 md:grid-cols-3">
            <Field label="Course format">
              <Select value={profile.format_preference} onChange={(event) => updateProfile('format_preference', event.target.value as StudentProfile['format_preference'])}>
                <option value="any">Any format</option>
                <option value="in-person">In person</option>
                <option value="hybrid">Hybrid</option>
                <option value="online">Online</option>
              </Select>
            </Field>
            <Field label="No classes before" optional>
              <Input type="time" value={constraints.earliest} onChange={(event) => onConstraintsChange({ ...constraints, earliest: event.target.value })} />
            </Field>
            <Field label="No classes after" optional>
              <Input type="time" value={constraints.latest} onChange={(event) => onConstraintsChange({ ...constraints, latest: event.target.value })} />
            </Field>
          </div>
          <div>
            <p className="mb-3 text-sm font-bold text-slate-800">Days off</p>
            <div className="flex flex-wrap gap-2">
              {weekdays.map((day) => {
                const selected = constraints.daysOff.includes(day)
                return (
                  <button
                    key={day}
                    type="button"
                    onClick={() => onConstraintsChange({ ...constraints, daysOff: selected ? constraints.daysOff.filter((item) => item !== day) : [...constraints.daysOff, day] })}
                    className={cn('rounded-full border px-4 py-2 text-xs font-extrabold transition', selected ? 'border-ucla-blue bg-ucla-blue text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-ucla-blue/40')}
                  >
                    {day.slice(0, 3)}
                  </button>
                )
              })}
            </div>
          </div>
          <Field label="Additional hard constraints" optional hint="Use one constraint per line, such as “No gaps longer than 90 minutes.”">
            <Textarea rows={3} value={constraints.additional} onChange={(event) => onConstraintsChange({ ...constraints, additional: event.target.value })} placeholder={'No gaps longer than 90 minutes\nNo more than 180 minutes consecutive'} />
          </Field>

          <Accordion type="single" collapsible className="rounded-xl border border-slate-200 px-4">
            <AccordionItem value="ranking">
              <AccordionTrigger><span className="flex items-center gap-2"><SlidersHorizontal className="size-4 text-ucla-blue" /> Advanced ranking weights</span></AccordionTrigger>
              <AccordionContent>
                <p className="mb-4 text-sm leading-6 text-slate-600">Weights are normalized over evidence that is actually available. Missing ratings or grades are not treated as zero.</p>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                  {([
                    ['weight_enrollment_chance', 'Enrollment'],
                    ['weight_professor_rating', 'Professor'],
                    ['weight_avg_gpa', 'Average GPA'],
                    ['weight_schedule_quality', 'Schedule'],
                    ['weight_workload', 'Workload'],
                  ] as const).map(([key, label]) => (
                    <Field key={key} label={label}>
                      <Input type="number" min="0" max="1" step="0.05" value={profile[key]} onChange={(event) => updateProfile(key, Number(event.target.value))} />
                    </Field>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </CardContent>
      </Card>

      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}
      <div className="flex items-center justify-between gap-3">
        <Button type="button" variant="ghost" onClick={onBack}><ArrowLeft /> Back</Button>
        <Button type="button" variant="gold" size="lg" onClick={onRun} disabled={loading}>
          <Play className="fill-current" /> {loading ? `Planning ${terms.length} quarter${terms.length > 1 ? 's' : ''}…` : `Run ${mode === 'year' ? 'academic-year' : 'quarter'} planner`}
        </Button>
      </div>
    </div>
  )
}
