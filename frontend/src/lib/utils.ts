import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function parseCourseList(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\n,;]+/)
        .map((course) => course.trim().toUpperCase().replace(/\s+/g, ' '))
        .filter(Boolean),
    ),
  )
}

export function formatCourseList(courses: string[]): string {
  return courses.join('\n')
}

export function clock(minutes: number): string {
  const hour = Math.floor(minutes / 60)
  const minute = minutes % 60
  const suffix = hour < 12 ? 'am' : 'pm'
  return `${hour % 12 || 12}:${minute.toString().padStart(2, '0')}${suffix}`
}
