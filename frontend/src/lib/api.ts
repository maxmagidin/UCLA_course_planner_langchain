import type {
  DarsParseResponse,
  HorizonPlanResponse,
  HorizonTerm,
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

export function parseDars(payload: { dars_text?: string; dars_pdf_base64?: string }): Promise<DarsParseResponse> {
  return request('/api/dars/parse', { method: 'POST', body: JSON.stringify(payload) })
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

export function autofillProfile(
  conversation: string,
  model: ModelConfig,
  darsCourses: string[],
): Promise<StudentProfile> {
  const courseContext = darsCourses.length
    ? `\nCourses already found in DARS: ${darsCourses.join(', ')}.`
    : ''
  return request('/api/intake', {
    method: 'POST',
    body: JSON.stringify({
      conversation: [{ role: 'user', content: `${conversation}${courseContext}` }],
      model,
    }),
  })
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
