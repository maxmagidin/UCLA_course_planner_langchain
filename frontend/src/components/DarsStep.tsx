import { FileCheck2, FileText, LockKeyhole, UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, Textarea } from '@/components/ui/field'
import { cn } from '@/lib/utils'

interface DarsStepProps {
  darsText: string
  onDarsTextChange: (value: string) => void
  file: File | null
  onFileChange: (file: File | null) => void
  parsed: boolean
  loading: boolean
  status: string
  error: string
  onParse: () => void
  onContinue: () => void
  onDemo: () => void
}

export function DarsStep({
  darsText,
  onDarsTextChange,
  file,
  onFileChange,
  parsed,
  loading,
  status,
  error,
  onParse,
  onContinue,
  onDemo,
}: DarsStepProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const chooseFile = (nextFile?: File) => {
    if (nextFile) onFileChange(nextFile)
  }

  return (
    <div className="space-y-5">
      <Card className="overflow-hidden">
        <div className="h-1.5 bg-gradient-to-r from-ucla-blue via-sky-400 to-ucla-gold" />
        <CardHeader className="gap-3 border-b border-slate-100 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Badge variant="gold">Step 1 · Degree audit</Badge>
            <CardTitle className="mt-3 text-2xl sm:text-3xl">Start with your DARS</CardTitle>
            <CardDescription className="mt-2 max-w-2xl">
              Upload the PDF or paste its text. The parser finds completed and in-progress course codes, then you approve the list.
            </CardDescription>
          </div>
          <div className="flex shrink-0 items-center gap-2 rounded-full bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">
            <LockKeyhole className="size-3.5" /> Local API processing
          </div>
        </CardHeader>
        <CardContent className="grid gap-6 pt-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,.95fr)]">
          <div className="space-y-4">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                chooseFile(event.dataTransfer.files[0])
              }}
              className={cn(
                'flex min-h-56 w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition outline-none focus-visible:ring-3 focus-visible:ring-ucla-gold/50',
                dragging ? 'border-ucla-blue bg-ucla-blue-soft' : 'border-slate-300 bg-slate-50/70 hover:border-ucla-blue/60 hover:bg-ucla-blue-soft/40',
              )}
            >
              <span className="mb-4 grid size-14 place-items-center rounded-2xl bg-white text-ucla-blue shadow-sm">
                {file ? <FileCheck2 className="size-7" /> : <UploadCloud className="size-7" />}
              </span>
              <strong className="text-base text-slate-950">{file ? file.name : 'Drop your DARS PDF here'}</strong>
              <span className="mt-1 text-sm text-slate-500">{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · click to replace` : 'or click to choose a file · up to 15 MB'}</span>
            </button>
            <input
              ref={inputRef}
              className="sr-only"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => chooseFile(event.target.files?.[0])}
            />
            <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-[.18em] text-slate-400">
              <span className="h-px flex-1 bg-slate-200" /> or paste text <span className="h-px flex-1 bg-slate-200" />
            </div>
            <Field label="DARS text" optional>
              <Textarea
                rows={6}
                value={darsText}
                onChange={(event) => onDarsTextChange(event.target.value)}
                placeholder="Paste the text from your UCLA degree audit…"
              />
            </Field>
          </div>

          <div className="flex min-w-0 flex-col justify-between rounded-2xl border border-slate-200 bg-slate-50/65 p-6">
            <div>
              <div className="flex items-center gap-3"><span className="grid size-11 place-items-center rounded-xl bg-white text-ucla-blue shadow-sm"><FileText className="size-5" /></span><div><p className="text-xs font-black uppercase tracking-[.16em] text-ucla-blue">One source of truth</p><h3 className="mt-1 text-lg font-extrabold text-slate-950">Import first, review next</h3></div></div>
              <p className="mt-5 text-sm leading-6 text-slate-600">DARS parsing extracts student fields and course buckets. On the next screen you can inspect and correct each value before any schedule is built.</p>
              <div className="mt-5 space-y-3 text-sm text-slate-700"><p className="flex gap-2"><span className="font-black text-ucla-blue">1.</span> Upload a DARS PDF or paste exported text.</p><p className="flex gap-2"><span className="font-black text-ucla-blue">2.</span> Read the audit with the local planner API.</p><p className="flex gap-2"><span className="font-black text-ucla-blue">3.</span> Review the parsed profile and completed, in-progress, remaining, and unclassified buckets.</p></div>
            </div>
            <div className="mt-8 flex items-center gap-2 text-xs text-slate-500"><FileText className="size-4 text-ucla-blue" /> You can continue with manual fields if parsing is unavailable.</div>
          </div>
        </CardContent>
      </Card>

      {(status || error) && (
        <div role={error ? 'alert' : 'status'} className={cn('rounded-xl border px-4 py-3 text-sm font-semibold', error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700')}>
          {error || status}
        </div>
      )}

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Button type="button" variant="ghost" onClick={onDemo}>Load a test student</Button>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button type="button" variant="outline" onClick={onContinue}>Continue without parsing</Button>
          <Button type="button" size="lg" onClick={parsed ? onContinue : onParse} disabled={loading}>
            {loading ? 'Reading DARS…' : parsed ? 'Approve and continue' : 'Read DARS'}
          </Button>
        </div>
      </div>
    </div>
  )
}
