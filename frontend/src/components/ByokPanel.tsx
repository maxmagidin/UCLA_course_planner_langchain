import { Bot, KeyRound, ShieldCheck, WandSparkles } from 'lucide-react'
import { useState } from 'react'

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field, Input, Select, Textarea } from '@/components/ui/field'
import type { ModelConfig } from '@/types'

const presets = {
  openai: { label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  openrouter: { label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o-mini' },
  asi: { label: 'ASI:One', baseUrl: 'https://api.asi1.ai/v1', model: 'asi1' },
  custom: { label: 'Custom compatible API', baseUrl: '', model: '' },
} as const

type Provider = keyof typeof presets

interface ByokPanelProps {
  loading: boolean
  status: string
  error: string
  onAutofill: (description: string, model: ModelConfig) => Promise<void>
}

export function ByokPanel({ loading, status, error, onAutofill }: ByokPanelProps) {
  const [provider, setProvider] = useState<Provider>('openai')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState<string>(presets.openai.baseUrl)
  const [modelName, setModelName] = useState<string>(presets.openai.model)
  const [description, setDescription] = useState('')

  const chooseProvider = (nextProvider: Provider) => {
    setProvider(nextProvider)
    setBaseUrl(presets[nextProvider].baseUrl)
    setModelName(presets[nextProvider].model)
  }

  const submit = async () => {
    await onAutofill(description, {
      provider: provider === 'asi' ? 'asi_one' : 'openai_compatible',
      api_key: apiKey,
      base_url: baseUrl,
      model: modelName,
      temperature: 0,
    })
  }

  return (
    <div className="rounded-2xl border border-ucla-blue/15 bg-ucla-blue-soft/45 px-5">
      <Accordion type="single" collapsible>
        <AccordionItem value="byok">
          <AccordionTrigger>
            <span className="flex min-w-0 items-center gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-ucla-blue shadow-sm"><Bot className="size-5" /></span>
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">Optional model autofill <Badge variant="outline">BYOK</Badge></span>
                <span className="mt-0.5 block text-xs font-medium text-slate-500">Describe your situation and use your own provider key to fill this form.</span>
              </span>
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <div className="mb-5 grid gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 sm:grid-cols-[auto_1fr]">
              <ShieldCheck className="mt-0.5 size-5" />
              <p className="leading-6"><strong>Request-only key.</strong> It stays in this browser component until you leave the page and is sent only to the intake endpoint. It is not stored in planner state, reports, checkpoints, or browser storage.</p>
            </div>
            <Field label="Describe your plan">
              <Textarea
                rows={4}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="I’m a junior Computer Science major with 96 units. I prefer classes after 10am, need Fridays free, and want to take CS 111 this fall…"
              />
            </Field>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field label="Provider">
                <Select value={provider} onChange={(event) => chooseProvider(event.target.value as Provider)}>
                  {Object.entries(presets).map(([value, preset]) => <option key={value} value={value}>{preset.label}</option>)}
                </Select>
              </Field>
              <Field label="API key">
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3.5 top-3.5 size-4 text-slate-400" />
                  <Input className="pl-10" type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Used for this request only" />
                </div>
              </Field>
              <Field label="Model">
                <Input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="Model name" />
              </Field>
              <Field label="OpenAI-compatible base URL">
                <Input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://…/v1" />
              </Field>
            </div>
            {(status || error) && <p role={error ? 'alert' : 'status'} className={`mt-4 text-sm font-semibold ${error ? 'text-red-700' : 'text-emerald-700'}`}>{error || status}</p>}
            <Button className="mt-5" type="button" variant="secondary" onClick={submit} disabled={loading || !apiKey || !description || !baseUrl || !modelName}>
              <WandSparkles /> {loading ? 'Autofilling…' : 'Autofill and review'}
            </Button>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}
