import * as React from 'react'

import { cn } from '@/lib/utils'

export const controlClass = 'w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus:border-ucla-blue focus:ring-3 focus:ring-ucla-blue/12 disabled:bg-slate-50 disabled:text-slate-500'

interface FieldProps extends React.ComponentProps<'label'> {
  label: string
  hint?: string
  optional?: boolean
}

function Field({ label, hint, optional, className, children, ...props }: FieldProps) {
  return (
    <label className={cn('flex min-w-0 flex-col gap-2', className)} {...props}>
      <span className="flex items-baseline justify-between gap-3 text-sm font-bold text-slate-800">
        {label}
        {optional && <span className="text-[11px] font-semibold text-slate-400">Optional</span>}
      </span>
      {children}
      {hint && <span className="text-xs leading-5 text-slate-500">{hint}</span>}
    </label>
  )
}

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(controlClass, 'h-11', className)} {...props} />
))
Input.displayName = 'Input'

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<'textarea'>>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(controlClass, 'min-h-24 resize-y', className)} {...props} />
))
Textarea.displayName = 'Textarea'

const Select = React.forwardRef<HTMLSelectElement, React.ComponentProps<'select'>>(({ className, ...props }, ref) => (
  <select ref={ref} className={cn(controlClass, 'h-11 appearance-auto', className)} {...props} />
))
Select.displayName = 'Select'

export { Field, Input, Select, Textarea }
