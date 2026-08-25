import { Code2, HeartPulse, Shield, Workflow } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { DarsStep } from '@/components/DarsStep'
import { PlanningStep } from '@/components/PlanningStep'
import { ProfileStep } from '@/components/ProfileStep'
import { ResultsStep } from '@/components/ResultsStep'
import { StepRail } from '@/components/StepRail'
import { Badge } from '@/components/ui/badge'
import { apiHostLabel, autofillProfile, checkHealth, fileToBase64, parseDars, runHorizon, suggestRoadmap } from '@/lib/api'
import { formatCourseList, parseCourseList } from '@/lib/utils'
import type { ConstraintsState, EditableTerm, HorizonPlanResponse, ModelConfig, StudentProfile } from '@/types'

const currentYear = new Date().getFullYear()

const defaultProfile: StudentProfile = {
  name: '',
  major: '',
  year: 'junior',
  gpa: 0,
  units_completed: 0,
  enrollment_pass: 'open',
  pass_open_datetime: '',
  term: `Fall ${currentYear}`,
  dars_courses: [],
  dars_in_progress_courses: [],
  dars_remaining_courses: [],
  required_courses: [],
  preferred_courses: [],
  hard_constraints: [],
  format_preference: 'any',
  min_units: 12,
  max_units: 16,
  weight_enrollment_chance: 0.25,
  weight_professor_rating: 0.2,
  weight_avg_gpa: 0.2,
  weight_schedule_quality: 0.2,
  weight_workload: 0.15,
}

const defaultConstraints: ConstraintsState = {
  daysOff: [],
  earliest: '',
  latest: '',
  additional: '',
}

function termId(label: string) {
  return label.toLowerCase().replace(/\s+/g, '-')
}

function blankTerm(label: string): EditableTerm {
  return { id: termId(label), term: label, requiredText: '', preferredText: '', minUnits: 12, maxUnits: 16 }
}

function academicTerms(year: number, includeSummer: boolean): EditableTerm[] {
  const labels = [`Fall ${year}`, `Winter ${year + 1}`, `Spring ${year + 1}`]
  if (includeSummer) labels.push(`Summer ${year + 1}`)
  return labels.map(blankTerm)
}

function timeConstraint(prefix: string, value: string): string {
  if (!value) return ''
  const [hourText, minute = '00'] = value.split(':')
  const hour = Number(hourText)
  const suffix = hour < 12 ? 'am' : 'pm'
  return `${prefix} ${hour % 12 || 12}:${minute} ${suffix}`
}

function App() {
  const [step, setStep] = useState(0)
  const [highestStep, setHighestStep] = useState(0)
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)

  const [darsText, setDarsText] = useState('')
  const [darsFile, setDarsFile] = useState<File | null>(null)
  const [coursesText, setCoursesText] = useState('')
  const [inProgressCoursesText, setInProgressCoursesText] = useState('')
  const [remainingCoursesText, setRemainingCoursesText] = useState('')
  const [darsParsed, setDarsParsed] = useState(false)
  const [darsLoading, setDarsLoading] = useState(false)
  const [darsStatus, setDarsStatus] = useState('')
  const [darsError, setDarsError] = useState('')

  const [profile, setProfile] = useState<StudentProfile>(defaultProfile)
  const [profileError, setProfileError] = useState('')
  const [autofillLoading, setAutofillLoading] = useState(false)
  const [autofillStatus, setAutofillStatus] = useState('')
  const [autofillError, setAutofillError] = useState('')

  const [mode, setMode] = useState<'quarter' | 'year'>('quarter')
  const [academicYear, setAcademicYear] = useState(currentYear)
  const [includeSummer, setIncludeSummer] = useState(false)
  const [terms, setTerms] = useState<EditableTerm[]>([blankTerm(`Fall ${currentYear}`)])
  const [constraints, setConstraints] = useState<ConstraintsState>(defaultConstraints)
  const [planLoading, setPlanLoading] = useState(false)
  const [planProgress, setPlanProgress] = useState('')
  const [planError, setPlanError] = useState('')
  const [roadmapLoading, setRoadmapLoading] = useState(false)
  const [roadmapStatus, setRoadmapStatus] = useState('')
  const [response, setResponse] = useState<HorizonPlanResponse | null>(null)
  const planAbortRef = useRef<AbortController | null>(null)

  const completedCourses = useMemo(() => parseCourseList(coursesText), [coursesText])

  useEffect(() => {
    checkHealth().then(() => setApiOnline(true)).catch(() => setApiOnline(false))
  }, [])

  const goTo = (nextStep: number) => {
    if (nextStep <= highestStep) {
      setStep(nextStep)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const advance = (nextStep: number) => {
    setHighestStep((current) => Math.max(current, nextStep))
    setStep(nextStep)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const readDars = async () => {
    setDarsError('')
    setDarsStatus('')
    if (!darsFile && !darsText.trim()) {
      setDarsError('Choose a DARS PDF or paste its text first.')
      return
    }
    if (darsFile && darsFile.size > 15 * 1024 * 1024) {
      setDarsError('The DARS PDF must be 15 MB or smaller.')
      return
    }
    setDarsLoading(true)
    try {
      const result = darsFile
        ? await parseDars({ dars_pdf_base64: await fileToBase64(darsFile) })
        : await parseDars({ dars_text: darsText })
      const eligible = result.completed_courses
      const remaining = [...result.remaining_courses, ...result.unclassified_courses]
      setCoursesText(formatCourseList(eligible))
      setInProgressCoursesText(formatCourseList(result.in_progress_courses))
      setRemainingCoursesText(formatCourseList(remaining))
      setProfile((current) => ({
        ...current,
        ...result.profile_hints,
        dars_courses: eligible,
        dars_in_progress_courses: result.in_progress_courses,
        dars_remaining_courses: remaining,
      }))
      setDarsParsed(true)
      setDarsStatus(`Read ${result.character_count.toLocaleString()} characters: ${eligible.length} completed, ${result.in_progress_courses.length} in progress, ${result.remaining_courses.length} remaining, and ${result.unclassified_courses.length} needing review.`)
    } catch (error) {
      setDarsError(error instanceof Error ? error.message : 'Could not parse that DARS.')
    } finally {
      setDarsLoading(false)
    }
  }

  const continueFromDars = () => {
    setProfile((current) => ({
      ...current,
      dars_courses: completedCourses,
      dars_in_progress_courses: parseCourseList(inProgressCoursesText),
      dars_remaining_courses: parseCourseList(remainingCoursesText),
    }))
    advance(1)
  }

  const loadDemo = () => {
    const demoCourses = ['COM SCI 31', 'COM SCI 32', 'COM SCI 33', 'COM SCI 35L', 'MATH 31A']
    setDarsFile(null)
    setDarsText('Student Name: Alex Student\nMajor: Computer Science\nClass Level: Junior\nCumulative GPA: 3.60\nUnits Completed: 96\nCOURSES COMPLETED\nCOM SCI 31 A\nCOM SCI 32 A-\nCOM SCI 33 B+\nCOM SCI 35L A\nMATH 31A B+')
    setCoursesText(formatCourseList(demoCourses))
    setInProgressCoursesText('')
    setRemainingCoursesText('COM SCI 111\nCOM SCI 118\nCOM SCI 180')
    setDarsParsed(true)
    setDarsStatus('Test student loaded. The fields remain editable.')
    setProfile({
      ...defaultProfile,
      name: 'Alex Student',
      major: 'Computer Science',
      year: 'junior',
      gpa: 3.6,
      units_completed: 96,
      enrollment_pass: 'pass_1',
      pass_open_datetime: '2026-08-28 09:00',
      term: 'Fall 2026',
      dars_courses: demoCourses,
      dars_in_progress_courses: [],
      dars_remaining_courses: ['COM SCI 111', 'COM SCI 118', 'COM SCI 180'],
    })
    setMode('quarter')
    setTerms([{
      ...blankTerm('Fall 2026'),
      requiredText: 'COM SCI 111',
      minUnits: 5,
      maxUnits: 5,
    }])
    setConstraints(defaultConstraints)
  }

  const continueFromProfile = () => {
    setProfileError('')
    if (!profile.name.trim() || !profile.major.trim()) {
      setProfileError('Name and major are required before planning.')
      return
    }
    advance(2)
  }

  const useAutofill = async (description: string, model: ModelConfig) => {
    setAutofillError('')
    setAutofillStatus('')
    setAutofillLoading(true)
    try {
      const filled = await autofillProfile(description, model, completedCourses)
      setProfile((current) => ({
        ...current,
        ...filled,
        term: current.term,
        dars_courses: completedCourses,
        dars_in_progress_courses: parseCourseList(inProgressCoursesText),
        dars_remaining_courses: parseCourseList(remainingCoursesText),
      }))
      if (filled.required_courses.length || filled.preferred_courses.length) {
        setTerms((current) => current.map((term, index) => index === 0 ? {
          ...term,
          requiredText: formatCourseList(filled.required_courses),
          preferredText: formatCourseList(filled.preferred_courses),
        } : term))
      }
      if (filled.hard_constraints.length) {
        setConstraints((current) => ({ ...current, additional: filled.hard_constraints.join('\n') }))
      }
      setAutofillStatus('Autofill complete. Review every field before continuing.')
    } catch (error) {
      setAutofillError(error instanceof Error ? error.message : 'Model autofill failed.')
    } finally {
      setAutofillLoading(false)
    }
  }

  const changeMode = (nextMode: 'quarter' | 'year') => {
    setMode(nextMode)
    if (nextMode === 'year') {
      const nextTerms = academicTerms(academicYear, includeSummer)
      const first = terms[0]
      if (first) nextTerms[0] = { ...nextTerms[0], requiredText: first.requiredText, preferredText: first.preferredText, minUnits: first.minUnits, maxUnits: first.maxUnits }
      setTerms(nextTerms)
    } else {
      setTerms([terms[0] || blankTerm(`Fall ${academicYear}`)])
    }
  }

  const changeAcademicYear = (year: number) => {
    setAcademicYear(year)
    const nextTerms = academicTerms(year, includeSummer)
    setTerms(nextTerms.map((term, index) => ({ ...term, requiredText: terms[index]?.requiredText || '', preferredText: terms[index]?.preferredText || '', minUnits: terms[index]?.minUnits ?? 12, maxUnits: terms[index]?.maxUnits ?? 16 })))
  }

  const changeSummer = (include: boolean) => {
    setIncludeSummer(include)
    const nextTerms = academicTerms(academicYear, include)
    setTerms(nextTerms.map((term, index) => ({ ...term, requiredText: terms[index]?.requiredText || '', preferredText: terms[index]?.preferredText || '', minUnits: terms[index]?.minUnits ?? 12, maxUnits: terms[index]?.maxUnits ?? 16 })))
  }

  const runPlan = async () => {
    setPlanError('')
    const normalizedTerms = terms.map((term) => ({
      term: term.term.trim(),
      required_courses: parseCourseList(term.requiredText),
      preferred_courses: parseCourseList(term.preferredText),
      min_units: term.minUnits,
      max_units: term.maxUnits,
    }))
    const invalidTerm = normalizedTerms.find((term) => !term.term || term.max_units < term.min_units)
    if (invalidTerm) {
      setPlanError('Every quarter needs a term name and a valid minimum/maximum unit range.')
      return
    }
    const emptyTerm = normalizedTerms.find((term) => !term.required_courses.length && !term.preferred_courses.length)
    if (emptyTerm) {
      setPlanError(`Add at least one required or preferred course for ${emptyTerm.term}.`)
      return
    }
    const assignments = new Map<string, string>()
    for (const term of normalizedTerms) {
      for (const code of [...term.required_courses, ...term.preferred_courses]) {
        const previous = assignments.get(code)
        if (previous && previous !== term.term) {
          setPlanError(`${code} is assigned to both ${previous} and ${term.term}. Put each course in one quarter.`)
          return
        }
        assignments.set(code, term.term)
      }
    }
    const hardConstraints = [
      ...constraints.daysOff.map((day) => `${day} off`),
      timeConstraint('No classes before', constraints.earliest),
      timeConstraint('No classes after', constraints.latest),
      ...constraints.additional.split('\n').map((item) => item.trim()),
    ].filter(Boolean)
    const planningProfile: StudentProfile = {
      ...profile,
      term: normalizedTerms[0].term,
      dars_courses: completedCourses,
      required_courses: normalizedTerms[0].required_courses,
      preferred_courses: normalizedTerms[0].preferred_courses,
      hard_constraints: hardConstraints,
      min_units: normalizedTerms[0].min_units,
      max_units: normalizedTerms[0].max_units,
    }
    setPlanLoading(true)
    setPlanProgress('Submitting planning job…')
    const controller = new AbortController()
    planAbortRef.current = controller
    try {
      const result = await runHorizon(
        planningProfile,
        normalizedTerms,
        (job) => setPlanProgress(`${job.message} ${job.progress}%`),
        controller.signal,
      )
      setProfile(planningProfile)
      setResponse(result)
      advance(3)
    } catch (error) {
      setPlanError(error instanceof Error ? error.message : 'The planner could not complete this run.')
    } finally {
      planAbortRef.current = null
      setPlanLoading(false)
      setPlanProgress('')
    }
  }

  const cancelPlan = () => {
    setPlanProgress('Requesting cancellation…')
    planAbortRef.current?.abort()
  }

  const autoPlaceAuditCourses = async () => {
    const remaining = parseCourseList(remainingCoursesText)
    if (!remaining.length) {
      setPlanError('Step 1 does not contain any remaining audit courses to place.')
      return
    }
    setPlanError('')
    setRoadmapStatus('')
    setRoadmapLoading(true)
    const horizonTerms = terms.map((term) => ({
      term: term.term,
      required_courses: [],
      preferred_courses: [],
      min_units: term.minUnits,
      max_units: term.maxUnits,
    }))
    try {
      const suggestion = await suggestRoadmap(profile, remaining, horizonTerms)
      setTerms((current) => current.map((term) => {
        const placement = suggestion.terms.find((item) => item.term === term.term)
        return {
          ...term,
          requiredText: formatCourseList(placement?.courses || []),
          preferredText: '',
        }
      }))
      const placed = suggestion.terms.reduce((total, term) => total + term.courses.length, 0)
      const warning = suggestion.warnings.length
        ? ` ${suggestion.warnings.slice(0, 3).join(' ')}${suggestion.warnings.length > 3 ? ` +${suggestion.warnings.length - 3} more warnings.` : ''}`
        : ''
      setRoadmapStatus(`Placed ${placed} course${placed === 1 ? '' : 's'} in the earliest prerequisite-safe terms.${warning}`)
    } catch (error) {
      setPlanError(error instanceof Error ? error.message : 'Could not build the prerequisite roadmap.')
    } finally {
      setRoadmapLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-page text-slate-900">
      <header className="border-b border-white/10 bg-ucla-blue-dark text-white">
        <div className="mx-auto flex w-full max-w-[1440px] items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <a href="/app/" className="flex min-w-0 items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-ucla-gold text-sm font-black tracking-tight text-ucla-blue-dark">UCLA</span>
            <span className="min-w-0"><strong className="block truncate text-sm font-extrabold sm:text-base">Course Planner</strong><small className="hidden text-xs text-sky-200 sm:block">LangChain + LangGraph rebuild</small></span>
          </a>
          <div className="flex items-center gap-2 sm:gap-3">
            <Badge variant="warning" className="hidden sm:inline-flex">Work in progress</Badge>
            <span className={`flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1.5 text-[11px] font-bold ${apiOnline === false ? 'text-red-200' : 'text-sky-100'}`} title={`API: ${apiHostLabel()}`}>
              <HeartPulse className="size-3.5" /> {apiOnline === null ? 'Checking API' : apiOnline ? 'API ready' : 'API offline'}
            </span>
            <a className="grid size-9 place-items-center rounded-lg text-sky-100 transition hover:bg-white/10 hover:text-white" href="https://github.com/maxmagidin/UCLA_course_planner_langchain/tree/langchain-migration" target="_blank" rel="noreferrer" aria-label="Open GitHub repository"><Code2 className="size-5" /></a>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden border-b border-slate-200 bg-white">
        <div className="absolute inset-y-0 right-0 w-1/2 bg-[radial-gradient(circle_at_center,rgba(39,116,174,.12),transparent_65%)]" />
        <div className="relative mx-auto grid w-full max-w-[1440px] gap-5 px-4 py-8 sm:px-6 sm:py-10 lg:grid-cols-[1fr_auto] lg:items-end lg:px-8">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] text-ucla-blue"><Workflow className="size-4" /> Deterministic degree planning</div>
            <h1 className="max-w-4xl text-3xl font-black tracking-[-.035em] text-slate-950 sm:text-5xl">From degree audit to a quarter—or a year.</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600 sm:text-base">Bring your DARS, review the facts, choose when courses should happen, and run the same evidence-backed workflow through the browser, API, CLI, or Python.</p>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-bold text-emerald-800"><Shield className="size-4" /> No model key required · BYOK is optional</div>
        </div>
      </section>

      <main className="mx-auto grid w-full max-w-[1440px] gap-6 px-0 py-0 sm:px-6 sm:py-6 lg:grid-cols-[260px_minmax(0,1fr)] lg:px-8 lg:py-8">
        <StepRail current={step} highest={highestStep} onNavigate={goTo} />
        <section className="min-w-0 px-4 pb-12 sm:px-0">
          {step === 0 && <DarsStep darsText={darsText} onDarsTextChange={setDarsText} file={darsFile} onFileChange={setDarsFile} coursesText={coursesText} onCoursesTextChange={setCoursesText} inProgressCoursesText={inProgressCoursesText} onInProgressCoursesTextChange={setInProgressCoursesText} remainingCoursesText={remainingCoursesText} onRemainingCoursesTextChange={setRemainingCoursesText} parsed={darsParsed} loading={darsLoading} status={darsStatus} error={darsError} onParse={readDars} onContinue={continueFromDars} onDemo={loadDemo} />}
          {step === 1 && <ProfileStep profile={profile} onChange={setProfile} completedCourseCount={completedCourses.length} error={profileError} autofillLoading={autofillLoading} autofillStatus={autofillStatus} autofillError={autofillError} onAutofill={useAutofill} onBack={() => setStep(0)} onContinue={continueFromProfile} />}
          {step === 2 && <PlanningStep mode={mode} onModeChange={changeMode} academicYear={academicYear} onAcademicYearChange={changeAcademicYear} includeSummer={includeSummer} onIncludeSummerChange={changeSummer} terms={terms} onTermsChange={setTerms} auditRemainingCourses={parseCourseList(remainingCoursesText)} roadmapLoading={roadmapLoading} roadmapStatus={roadmapStatus} onAutoPlace={autoPlaceAuditCourses} profile={profile} onProfileChange={setProfile} constraints={constraints} onConstraintsChange={setConstraints} loading={planLoading} progress={planProgress} error={planError} onBack={() => setStep(1)} onRun={runPlan} onCancel={cancelPlan} />}
          {step === 3 && response && <ResultsStep response={response} studentName={profile.name} onEdit={() => setStep(2)} onStartOver={() => window.location.reload()} />}
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-3 px-6 py-6 text-xs leading-5 text-slate-500 sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <p>Work in progress. Verify recommendations against official UCLA advising and enrollment systems.</p>
          <div className="flex gap-4"><a className="font-bold text-ucla-blue hover:underline" href="/docs" target="_blank" rel="noreferrer">API docs</a><a className="font-bold text-ucla-blue hover:underline" href="https://github.com/maxmagidin/UCLA_course_planner_langchain/tree/langchain-migration" target="_blank" rel="noreferrer">Fork on GitHub</a></div>
        </div>
      </footer>
    </div>
  )
}

export default App
