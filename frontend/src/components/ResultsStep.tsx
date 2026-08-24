import { AlertTriangle, ArrowLeft, BookOpenCheck, CalendarCheck2, CheckCircle2, Download, ExternalLink, MapPin, RotateCcw, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { clock, cn } from '@/lib/utils'
import type { HorizonPlanResponse, HorizonTermResult, PlanStatus, ScheduleCandidate } from '@/types'

function statusVariant(status: PlanStatus) {
  if (status === 'completed') return 'success' as const
  if (status === 'partial') return 'warning' as const
  return 'danger' as const
}

function CandidateSummary({ candidate }: { candidate: ScheduleCandidate }) {
  const enrollment = Number.isFinite(candidate.min_enrollment_chance) ? candidate.min_enrollment_chance : 0
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {(candidate.courses || []).map((course) => <Badge key={course.course_code} className="px-3 py-1.5 text-xs">{course.course_code} · {course.units}u</Badge>)}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Units', candidate.total_units ?? 0],
          ['Campus days', candidate.days_on_campus ?? 0],
          ['Score', (candidate.composite_score ?? 0).toFixed(3)],
          ['Min. seat chance', `${Math.round(enrollment * 100)}%`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <span className="block text-[10px] font-black uppercase tracking-[.13em] text-slate-400">{label}</span>
            <strong className="mt-1 block text-lg text-slate-950">{value}</strong>
          </div>
        ))}
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200">
        <div className="grid grid-cols-[90px_minmax(0,1fr)] border-b border-slate-200 bg-slate-50 px-4 py-2 text-[10px] font-black uppercase tracking-[.13em] text-slate-500">
          <span>Day</span><span>Meeting times</span>
        </div>
        {(candidate.day_schedules || []).length ? candidate.day_schedules.map((day) => (
          <div key={day.day} className="grid grid-cols-[90px_minmax(0,1fr)] border-b border-slate-100 px-4 py-3 last:border-0">
            <strong className="text-sm text-slate-800">{day.day.slice(0, 3)}</strong>
            <div className="min-w-0 space-y-2">
              {(day.sections || []).map((meeting, index) => (
                <div key={`${meeting.course_code}-${meeting.section_id}-${index}`} className="flex min-w-0 flex-col gap-1 text-sm sm:flex-row sm:items-center sm:justify-between">
                  <span className="min-w-0"><strong className="text-ucla-blue-dark">{meeting.course_code}</strong> <span className="text-slate-500">{meeting.section_id} · {clock(meeting.start_min)}–{clock(meeting.end_min)}</span></span>
                  <span className="flex shrink-0 items-center gap-1 text-xs text-slate-400"><MapPin className="size-3" /> {meeting.location || 'TBA'}</span>
                </div>
              ))}
            </div>
          </div>
        )) : <p className="px-4 py-5 text-sm text-slate-500">No meeting-time rows were returned.</p>}
      </div>
    </div>
  )
}

function TermResultCard({ termResult, index }: { termResult: HorizonTermResult; index: number }) {
  const { result } = termResult
  const top = result.candidates?.[0]
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-slate-100 bg-slate-50/55 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[.16em] text-ucla-blue">Quarter {index + 1}</p>
          <CardTitle className="mt-1 text-xl">{termResult.term}</CardTitle>
          <CardDescription>{top ? `${result.candidates.length} valid schedule candidate${result.candidates.length === 1 ? '' : 's'}` : 'No valid section-level schedule returned'}</CardDescription>
        </div>
        <Badge variant={statusVariant(result.status)}>{result.status}</Badge>
      </CardHeader>
      <CardContent className="pt-6">
        {top ? <CandidateSummary candidate={top} /> : (
          <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
            <AlertTriangle className="mt-0.5 size-5 shrink-0" />
            <div><strong>Nothing could be scheduled for this term.</strong><p className="mt-1 leading-6">Check whether UCLA has published the term, whether every required course is offered, and whether the unit and time constraints can be satisfied.</p></div>
          </div>
        )}

        {!!result.errors?.length && (
          <div className="mt-5 space-y-2">
            {result.errors.map((error, errorIndex) => (
              <div key={`${error.node}-${errorIndex}`} className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"><strong>{error.node}:</strong> {error.message}</div>
            ))}
          </div>
        )}

        <Accordion type="multiple" className="mt-5 rounded-xl border border-slate-200 px-4">
          <AccordionItem value="alternatives">
            <AccordionTrigger>Alternative schedules ({Math.max(0, (result.candidates?.length || 0) - 1)})</AccordionTrigger>
            <AccordionContent>
              {(result.candidates || []).slice(1, 4).length ? (
                <div className="space-y-3">
                  {result.candidates.slice(1, 4).map((candidate) => (
                    <div key={candidate.rank} className="flex flex-col gap-2 rounded-xl bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div><strong className="text-sm text-slate-900">Rank #{candidate.rank}</strong><p className="mt-1 text-xs text-slate-500">{candidate.courses.map((course) => course.course_code).join(' · ')}</p></div>
                      <Badge variant="outline">Score {(candidate.composite_score ?? 0).toFixed(3)}</Badge>
                    </div>
                  ))}
                </div>
              ) : <p className="text-sm text-slate-500">No additional candidates were returned.</p>}
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="evidence">
            <AccordionTrigger>Evidence and data freshness</AccordionTrigger>
            <AccordionContent>
              <div className="grid gap-3 md:grid-cols-2">
                {Object.entries(result.evidence || {}).map(([name, evidence]) => (
                  <div key={name} className="rounded-xl border border-slate-200 p-4">
                    <div className="flex items-center justify-between gap-3"><strong className="text-sm text-slate-900">{name}</strong><Badge variant={statusVariant(evidence.status === 'ok' ? 'completed' : evidence.status === 'partial' ? 'partial' : 'failed')}>{evidence.status}</Badge></div>
                    <p className="mt-2 text-xs leading-5 text-slate-500">{evidence.detail}</p>
                  </div>
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="report">
            <AccordionTrigger>Full Markdown report</AccordionTrigger>
            <AccordionContent>
              <article className="report-markdown rounded-xl border border-slate-200 bg-white p-5">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.report_markdown || 'No report was returned.'}</ReactMarkdown>
              </article>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  )
}

interface ResultsStepProps {
  response: HorizonPlanResponse
  studentName: string
  onEdit: () => void
  onStartOver: () => void
}

export function ResultsStep({ response, studentName, onEdit, onStartOver }: ResultsStepProps) {
  const plannedCount = response.terms.reduce((total, term) => total + term.planned_courses.length, 0)
  const downloadReports = () => {
    const markdown = response.terms.map((term) => `<!-- ${term.term} -->\n\n${term.result.report_markdown}`).join('\n\n---\n\n')
    const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `ucla-course-plan-${response.run_id.slice(0, 8)}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      <Card className="overflow-hidden border-ucla-blue/20 bg-ucla-blue-dark text-white">
        <div className="relative p-6 sm:p-8">
          <Sparkles className="absolute right-6 top-6 size-24 text-white/5" />
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <Badge variant={statusVariant(response.status)}>{response.status}</Badge>
              <h2 className="mt-4 text-3xl font-black tracking-tight sm:text-4xl">{studentName ? `${studentName}’s plan` : 'Your UCLA course plan'}</h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-sky-100">{response.terms.length} quarter{response.terms.length === 1 ? '' : 's'} evaluated · {plannedCount} course placements in top-ranked schedules · run {response.run_id.slice(0, 8)}</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="outline" className="border-white/25 bg-white/10 text-white hover:bg-white/20" onClick={onEdit}><ArrowLeft /> Edit plan</Button>
              <Button type="button" variant="gold" onClick={downloadReports}><Download /> Download report</Button>
            </div>
          </div>
        </div>
        <div className="grid border-t border-white/10 bg-white/5 sm:grid-cols-3">
          <div className="flex items-center gap-3 border-b border-white/10 p-4 sm:border-b-0 sm:border-r"><CalendarCheck2 className="size-5 text-ucla-gold" /><span><strong className="block text-lg">{response.terms.length}</strong><small className="text-sky-100">quarters evaluated</small></span></div>
          <div className="flex items-center gap-3 border-b border-white/10 p-4 sm:border-b-0 sm:border-r"><BookOpenCheck className="size-5 text-ucla-gold" /><span><strong className="block text-lg">{plannedCount}</strong><small className="text-sky-100">planned placements</small></span></div>
          <div className="flex items-center gap-3 p-4"><CheckCircle2 className="size-5 text-ucla-gold" /><span><strong className="block text-lg">{response.completed_courses.length}</strong><small className="text-sky-100">courses after horizon</small></span></div>
        </div>
      </Card>

      <div className={cn('grid gap-5', response.terms.length > 1 && '2xl:grid-cols-2')}>
        {response.terms.map((term, index) => <TermResultCard key={`${term.term}-${index}`} termResult={term} index={index} />)}
      </div>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Button type="button" variant="ghost" onClick={onStartOver}><RotateCcw /> Start another plan</Button>
        <Button asChild variant="outline"><a href="/docs" target="_blank" rel="noreferrer">Open API documentation <ExternalLink /></a></Button>
      </div>
    </div>
  )
}
