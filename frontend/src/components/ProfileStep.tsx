import { ArrowLeft, ArrowRight, Info } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, Input, Select } from '@/components/ui/field'
import { ByokPanel } from '@/components/ByokPanel'
import type { ModelConfig, StudentProfile } from '@/types'

interface ProfileStepProps {
  profile: StudentProfile
  onChange: (profile: StudentProfile) => void
  completedCourseCount: number
  error: string
  autofillLoading: boolean
  autofillStatus: string
  autofillError: string
  onAutofill: (description: string, model: ModelConfig) => Promise<void>
  onBack: () => void
  onContinue: () => void
}

export function ProfileStep({
  profile,
  onChange,
  completedCourseCount,
  error,
  autofillLoading,
  autofillStatus,
  autofillError,
  onAutofill,
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
            <p className="leading-6"><strong>{completedCourseCount} DARS courses</strong> will be treated as completed or in progress for prerequisite checks. You can edit them by returning to Step 1.</p>
          </div>
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

      <ByokPanel loading={autofillLoading} status={autofillStatus} error={autofillError} onAutofill={onAutofill} />

      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}
      <div className="flex items-center justify-between gap-3">
        <Button type="button" variant="ghost" onClick={onBack}><ArrowLeft /> Back</Button>
        <Button type="button" size="lg" onClick={onContinue}>Build planning horizon <ArrowRight /></Button>
      </div>
    </div>
  )
}
