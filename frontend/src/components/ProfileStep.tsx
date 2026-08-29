import { ArrowLeft, ArrowRight, Info, ListChecks } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, Input, Select } from '@/components/ui/field'
import type { StudentProfile } from '@/types'

interface ProfileStepProps {
  profile: StudentProfile
  onChange: (profile: StudentProfile) => void
  completedCourseCount: number
  completedCoursesText: string
  inProgressCoursesText: string
  remainingCoursesText: string
  unclassifiedCoursesText: string
  onCompletedCoursesChange: (value: string) => void
  onInProgressCoursesChange: (value: string) => void
  onRemainingCoursesChange: (value: string) => void
  onUnclassifiedCoursesChange: (value: string) => void
  missingFields: string[]
  warnings: string[]
  error: string
  onBack: () => void
  onContinue: () => void
}

export function ProfileStep({
  profile,
  onChange,
  completedCourseCount,
  completedCoursesText,
  inProgressCoursesText,
  remainingCoursesText,
  unclassifiedCoursesText,
  onCompletedCoursesChange,
  onInProgressCoursesChange,
  onRemainingCoursesChange,
  onUnclassifiedCoursesChange,
  missingFields,
  warnings,
  error,
  onBack,
  onContinue,
}: ProfileStepProps) {
  const update = <K extends keyof StudentProfile>(key: K, value: StudentProfile[K]) => {
    onChange({ ...profile, [key]: value })
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="border-b border-slate-100">
          <Badge variant="gold" className="w-fit">Step 2 · Student profile</Badge>
          <CardTitle className="mt-2 text-2xl sm:text-3xl">Confirm what the planner should know</CardTitle>
          <CardDescription className="max-w-2xl">
            DARS fills what it can. You stay in control of every value before it reaches the planning workflow.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950">
            <Info className="mt-0.5 size-5 shrink-0 text-ucla-blue" />
            <p className="leading-6"><strong>{completedCourseCount} completed DARS courses</strong> will be used for prerequisite checks. In-progress and remaining courses stay visible but do not unlock eligibility. Review every bucket before planning.</p>
          </div>
          {(missingFields.length > 0 || warnings.length > 0) && <div className="mb-6 space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950"><strong>Audit review notes</strong>{missingFields.length > 0 && <p>Missing fields: {missingFields.join(', ')}. Fill them in below.</p>}{warnings.map((warning) => <p key={warning}>⚠ {warning}</p>)}</div>}
          <div className="grid gap-5 md:grid-cols-2">
            <Field label="Name">
              <Input autoComplete="name" value={profile.name} onChange={(event) => update('name', event.target.value)} placeholder="Alex Student" />
            </Field>
            <Field label="Major">
              <Input value={profile.major} onChange={(event) => update('major', event.target.value)} placeholder="Computer Science" />
            </Field>
            <Field label="Class level">
              <Select value={profile.year} onChange={(event) => update('year', event.target.value as StudentProfile['year'])}>
                <option value="freshman">Freshman</option>
                <option value="sophomore">Sophomore</option>
                <option value="junior">Junior</option>
                <option value="senior">Senior</option>
                <option value="graduate">Graduate</option>
              </Select>
            </Field>
            <Field label="Cumulative GPA" hint="Used as student context; it does not override course eligibility data.">
              <Input type="number" min="0" max="4" step="0.01" value={profile.gpa} onChange={(event) => update('gpa', Number(event.target.value))} />
            </Field>
            <Field label="Units completed">
              <Input type="number" min="0" step="0.5" value={profile.units_completed} onChange={(event) => update('units_completed', Number(event.target.value))} />
            </Field>
            <Field label="Enrollment window">
              <Select value={profile.enrollment_pass} onChange={(event) => update('enrollment_pass', event.target.value as StudentProfile['enrollment_pass'])}>
                <option value="pass_1">First pass</option>
                <option value="pass_2">Second pass</option>
                <option value="open">Open enrollment</option>
              </Select>
            </Field>
            <Field label="Enrollment window opens" optional hint="Useful for interpreting enrollment risk.">
              <Input value={profile.pass_open_datetime} onChange={(event) => update('pass_open_datetime', event.target.value)} placeholder="2026-08-28 09:00" />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-slate-100">
          <div className="flex items-center gap-2"><ListChecks className="size-5 text-ucla-blue" /><CardTitle>Review DARS course buckets</CardTitle></div>
          <CardDescription>These are the parsed facts sent to the deterministic planner. Move uncertain entries to “Needs review”; completed entries alone satisfy prerequisite checks.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5 pt-6">
          <CourseBucket label="Completed" value={completedCoursesText} onChange={onCompletedCoursesChange} tone="emerald" hint="Counts toward prerequisites" />
          <CourseBucket label="In progress" value={inProgressCoursesText} onChange={onInProgressCoursesChange} tone="sky" hint="Does not unlock prerequisites yet" />
          <CourseBucket label="Remaining" value={remainingCoursesText} onChange={onRemainingCoursesChange} tone="amber" hint="Candidates to place or clarify" />
          <CourseBucket label="Unclassified" value={unclassifiedCoursesText} onChange={onUnclassifiedCoursesChange} tone="amber" hint="Needs manual review before use" />
        </CardContent>
      </Card>

      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}
      <div className="flex items-center justify-between gap-3">
        <Button type="button" variant="ghost" onClick={onBack}><ArrowLeft /> Back</Button>
        <Button type="button" size="lg" onClick={onContinue}>Build planning horizon <ArrowRight /></Button>
      </div>
    </div>
  )
}

function CourseBucket({ label, value, onChange, tone, hint }: { label: string; value: string; onChange: (value: string) => void; tone: 'emerald' | 'sky' | 'amber'; hint: string }) {
  const colors = { emerald: 'text-emerald-700', sky: 'text-sky-700', amber: 'text-amber-700' }
  return <div className="flex min-w-0 flex-col"><label className={`text-xs font-black uppercase tracking-[.13em] ${colors[tone]}`}>{label}</label><textarea className="mt-2 min-h-40 w-full resize-y rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 font-mono text-xs leading-6 text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-ucla-blue focus:ring-3 focus:ring-ucla-blue/12" value={value} onChange={(event) => onChange(event.target.value)} placeholder="One course per line" aria-label={label} /><span className="mt-2 text-xs leading-5 text-slate-500">{hint}</span></div>
}
