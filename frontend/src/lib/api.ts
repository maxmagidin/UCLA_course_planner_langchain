import type {
  DarsParseResponse,
  HorizonPlanResponse,
  HorizonTerm,
  EnhancementContext,
  EnhancementResponse,
  ModelConfig,
  PlannerJobResponse,
  RoadmapResponse,
  StudentProfile,
} from '@/types'

const configuredBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

function endpoint(path: string): string {
  return `${configuredBase}${path}`
}

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) return String(item.msg)
        return String(item)
      })
      .join(' ')
  }
  return 'The planner could not complete that request.'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isNumberRecord(value: unknown): value is Record<string, number> {
  return isRecord(value) && Object.values(value).every((item) => typeof item === 'number' && Number.isFinite(item))
}

function parseEnhancementResponse(value: unknown, context: EnhancementContext): EnhancementResponse {
  if (!isRecord(value) || value.requires_review !== true || !isRecord(value.proposal)) {
    throw new Error('The enhancement response was incomplete or did not require review. Nothing was changed.')
  }
  const proposal = value.proposal
  const terms = proposal.terms
  const validTerms = Array.isArray(terms) && terms.every((term) => isRecord(term)
    && typeof term.term === 'string'
    && isStringArray(term.required_courses)
    && isStringArray(term.preferred_courses)
    && typeof term.min_units === 'number'
    && typeof term.max_units === 'number')
  const validFormat = proposal.format_preference === 'in-person' || proposal.format_preference === 'hybrid' || proposal.format_preference === 'online' || proposal.format_preference === 'any'
  if (!validTerms || !validFormat || !isStringArray(proposal.hard_constraints) || !isNumberRecord(proposal.ranking_weights) || !isStringArray(value.explanations) || !isStringArray(value.warnings)) {
    throw new Error('The enhancement response did not match the planning proposal contract. Nothing was changed.')
  }
  const weights = proposal.ranking_weights
  const requiredWeights = ['weight_enrollment_chance', 'weight_professor_rating', 'weight_avg_gpa', 'weight_schedule_quality', 'weight_workload']
  if (!requiredWeights.every((key) => typeof weights[key] === 'number')) {
    throw new Error('The enhancement response omitted one or more ranking weights. Nothing was changed.')
  }
  const allowedTerms = new Set(context.terms.map((term) => term.term))
  const allowedCourses = new Set(context.allowed_courses.map((course) => course.trim().toUpperCase().replace(/\s+/g, ' ')))
  context.terms.forEach((term) => [...term.required_courses, ...term.preferred_courses].forEach((course) => allowedCourses.add(course.trim().toUpperCase().replace(/\s+/g, ' '))))
  for (const term of terms as Array<Record<string, unknown>>) {
    if (!allowedTerms.has(String(term.term))) throw new Error('The enhancement suggested a term outside this planning horizon. Nothing was changed.')
    if (Number(term.min_units) < 0 || Number(term.max_units) < Number(term.min_units)) throw new Error('The enhancement suggested an invalid unit range. Nothing was changed.')
    for (const course of [...(term.required_courses as string[]), ...(term.preferred_courses as string[])]) {
      if (!allowedCourses.has(course.trim().toUpperCase().replace(/\s+/g, ' '))) throw new Error('The enhancement suggested a course outside the reviewed allow-list. Nothing was changed.')
    }
  }
  return value as unknown as EnhancementResponse
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(endpoint(path), {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new Error('Could not reach the planner API. Make sure the FastAPI server is running.')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(detailMessage(body.detail))
  return body as T
}

export function checkHealth(): Promise<{ status: string }> {
  return request('/api/health')
}

export async function parseDars(payload: { dars_text?: string; dars_pdf_base64?: string }): Promise<DarsParseResponse> {
  const raw = await request<DarsParseResponse>('/api/dars/parse', { method: 'POST', body: JSON.stringify(payload) })
  // Keep the UI on the preferred shape while accepting the pre-migration response
  // during rollout. The normalization boundary also keeps parsing details out of
  // the workflow components.
  const courses = raw.courses || raw.course_buckets || {
    completed: raw.completed_courses || [],
    in_progress: raw.in_progress_courses || [],
    remaining: raw.remaining_courses || [],
    unclassified: raw.unclassified_courses || [],
  }
  return {
    ...raw,
    profile_draft: raw.profile_draft || raw.profile_hints || {},
    courses,
    missing_fields: raw.missing_fields || [],
    warnings: raw.warnings || [],
    completed_courses: courses.completed || [],
    in_progress_courses: courses.in_progress || [],
    remaining_courses: courses.remaining || [],
    unclassified_courses: courses.unclassified || [],
    profile_hints: raw.profile_hints || raw.profile_draft || {},
  }
}

export async function runHorizon(
  profile: StudentProfile,
  terms: HorizonTerm[],
  onProgress?: (job: PlannerJobResponse) => void,
  signal?: AbortSignal,
): Promise<HorizonPlanResponse> {
  const created = await request<PlannerJobResponse>('/api/plan/horizon/jobs', {
    method: 'POST',
    body: JSON.stringify({ profile, terms }),
  })
  onProgress?.(created)

  for (let attempt = 0; attempt < 1_800; attempt += 1) {
    if (signal?.aborted) {
      await request<PlannerJobResponse>(`/api/jobs/${created.id}`, { method: 'DELETE' }).catch(() => undefined)
      throw new Error('Planning cancelled.')
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1_000))
    const job = await request<PlannerJobResponse>(`/api/jobs/${created.id}`)
    onProgress?.(job)
    if (job.status === 'completed' && job.result) return job.result
    if (job.status === 'failed') throw new Error(job.error || job.message || 'The planning job failed.')
    if (job.status === 'cancelled') throw new Error('Planning cancelled.')
    if (job.status === 'interrupted') throw new Error('The server restarted before this planning job finished. Run it again.')
  }
  await request<PlannerJobResponse>(`/api/jobs/${created.id}`, { method: 'DELETE' }).catch(() => undefined)
  throw new Error('The planning job exceeded the 30-minute browser limit and was cancelled.')
}

export function suggestRoadmap(profile: StudentProfile, courses: string[], terms: HorizonTerm[]): Promise<RoadmapResponse> {
  return request('/api/roadmap/suggest', {
    method: 'POST',
    body: JSON.stringify({ profile, courses, terms }),
  })
}

export function enhancePlanning(
  description: string,
  context: EnhancementContext,
  model: ModelConfig,
): Promise<EnhancementResponse> {
  return request<unknown>('/api/planning/enhance', {
    method: 'POST',
    body: JSON.stringify({
      description,
      context,
      model,
    }),
  }).then((value) => parseEnhancementResponse(value, context))
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      resolve(result.includes(',') ? result.split(',', 2)[1] : result)
    }
    reader.onerror = () => reject(new Error('Could not read that PDF.'))
    reader.readAsDataURL(file)
  })
}

export function apiHostLabel(): string {
  return configuredBase || 'this server'
}
