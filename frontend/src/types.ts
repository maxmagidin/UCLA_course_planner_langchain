export type YearLevel = 'freshman' | 'sophomore' | 'junior' | 'senior' | 'graduate'
export type EnrollmentPass = 'pass_1' | 'pass_2' | 'open'
export type CourseFormat = 'in-person' | 'hybrid' | 'online' | 'any'
export type PlanStatus = 'completed' | 'partial' | 'failed'

export interface StudentProfile {
  name: string
  major: string
  year: YearLevel
  gpa: number
  units_completed: number
  enrollment_pass: EnrollmentPass
  pass_open_datetime: string
  term: string
  dars_courses: string[]
  required_courses: string[]
  preferred_courses: string[]
  hard_constraints: string[]
  format_preference: CourseFormat
  min_units: number
  max_units: number
  weight_enrollment_chance: number
  weight_professor_rating: number
  weight_avg_gpa: number
  weight_schedule_quality: number
  weight_workload: number
}

export interface HorizonTerm {
  term: string
  required_courses: string[]
  preferred_courses: string[]
  min_units: number
  max_units: number
}

export interface EditableTerm {
  id: string
  term: string
  requiredText: string
  preferredText: string
  minUnits: number
  maxUnits: number
}

export interface DarsParseResponse {
  source: 'text' | 'pdf'
  character_count: number
  course_codes: string[]
  profile_hints: Partial<Pick<StudentProfile, 'name' | 'major' | 'year' | 'gpa' | 'units_completed'>>
}

export interface ModelConfig {
  provider: string
  api_key: string
  base_url: string
  model: string
  temperature: number
}

export interface CourseChoice {
  course_code: string
  title: string
  units: number
  lecture_section_id?: string
  discussion_section_id?: string
}

export interface Meeting {
  course_code: string
  section_id: string
  start_min: number
  end_min: number
  instructor?: string
  location?: string
}

export interface DaySchedule {
  day: string
  sections: Meeting[]
  total_minutes: number
  gap_minutes: number
  max_consecutive_minutes: number
}

export interface ScheduleCandidate {
  courses: CourseChoice[]
  day_schedules: DaySchedule[]
  total_units: number
  days_on_campus: number
  avg_gap_minutes_per_day: number
  min_enrollment_chance: number
  schedule_quality_score: number
  composite_score: number
  preference_match_score: number
  rank: number
}

export interface EvidenceRecord {
  source: string
  fetched_at: string
  status: 'ok' | 'partial' | 'failed'
  detail: string
}

export interface RunError {
  node: string
  message: string
  recoverable: boolean
}

export interface PlannerResult {
  run_id: string
  status: PlanStatus
  report_markdown: string
  candidates: ScheduleCandidate[]
  evidence: Record<string, EvidenceRecord>
  errors: RunError[]
}

export interface HorizonTermResult {
  term: string
  planned_courses: string[]
  completed_courses_after_term: string[]
  result: PlannerResult
}

export interface HorizonPlanResponse {
  run_id: string
  status: PlanStatus
  terms: HorizonTermResult[]
  completed_courses: string[]
}

export interface ConstraintsState {
  daysOff: string[]
  earliest: string
  latest: string
  additional: string
}
