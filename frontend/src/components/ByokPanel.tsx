import { Bot, KeyRound, ShieldCheck, WandSparkles } from 'lucide-react'
import { useState } from 'react'

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Field, Input, Select, Textarea } from '@/components/ui/field'
import { enhancePlanning } from '@/lib/api'
import type { EnhancementContext, EnhancementProposal, EnhancementResponse, ModelConfig } from '@/types'

type ModelProvider = ModelConfig['provider']

const providerDefaults: Record<ModelProvider, { baseUrl: string; model: string }> = {
  openai: { baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  anthropic: { baseUrl: 'https://api.anthropic.com', model: 'claude-haiku-4-5-20251001' },
  openai_compatible: { baseUrl: 'http://host.docker.internal:11434/v1', model: 'llama3.2' },
}

interface ByokPanelProps {
  context: EnhancementContext
  onApply: (proposal: EnhancementProposal) => void
}

function proposalLines(proposal: EnhancementProposal): string[] {
  const terms = proposal.terms.map((term) => {
    const required = term.required_courses.length ? `required: ${term.required_courses.join(', ')}` : ''
    const preferred = term.preferred_courses.length ? `preferred: ${term.preferred_courses.join(', ')}` : ''
    return `${term.term} — ${[required, preferred].filter(Boolean).join('; ') || 'no course changes'}`
  })
  return [
    ...terms,
    `Format: ${proposal.format_preference}`,
    proposal.hard_constraints.length ? `Constraints: ${proposal.hard_constraints.join('; ')}` : 'Constraints: none',
    `Ranking weights: ${Object.entries(proposal.ranking_weights).map(([key, value]) => `${key.replace(/^weight_/, '')} ${value}`).join(', ') || 'unchanged'}`,
  ]
}

export function ByokPanel({ context, onApply }: ByokPanelProps) {
  const [open, setOpen] = useState(false)
  const [provider, setProvider] = useState<ModelProvider>('openai')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1')
  const [modelName, setModelName] = useState('gpt-4o-mini')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [result, setResult] = useState<EnhancementResponse | null>(null)

  const changeProvider = (next: ModelProvider) => {
    setProvider(next)
    setApiKey('')
    setBaseUrl(providerDefaults[next].baseUrl)
    setModelName(providerDefaults[next].model)
    setResult(null)
    setStatus('')
    setError('')
  }

  const submit = async () => {
    setError('')
    setStatus('')
    setResult(null)
    setLoading(true)
    try {
      const next = await enhancePlanning(description, context, { provider, api_key: apiKey, base_url: baseUrl, model: modelName, temperature: 0 })
      setResult(next)
      setStatus('Suggestion ready. Nothing changes until you apply it below.')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not create a suggestion.')
    } finally {
      // Never retain a BYOK secret after the request, including failed requests.
      setApiKey('')
      setLoading(false)
    }
  }

  return (
    <div className="rounded-2xl border border-ucla-blue/15 bg-ucla-blue-soft/45 px-5">
      <Accordion type="single" collapsible value={open ? 'byok' : undefined} onValueChange={(value) => setOpen(value === 'byok')}>
        <AccordionItem value="byok">
          <AccordionTrigger>
            <span className="flex min-w-0 items-center gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-ucla-blue shadow-sm"><Bot className="size-5" /></span>
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">Optional preference translation <Badge variant="outline">BYOK or local</Badge></span>
                <span className="mt-0.5 block text-xs font-medium text-slate-500">Describe preferences in plain language; review the proposal before applying it.</span>
              </span>
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <div className="mb-5 grid gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 sm:grid-cols-[auto_1fr]">
              <ShieldCheck className="mt-0.5 size-5" />
              <p className="leading-6"><strong>Optional and request-only.</strong> Your preference text and any supplied key go through this local planner backend to the provider you choose (not directly from this browser). The key is cleared as soon as the request finishes. A custom provider receives the preference text and any key you enter. The model cannot change DARS facts, prerequisites, UCLA facts, ratings, or ranking code.</p>
            </div>
            <Field label="Describe your preferences">
              <Textarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="I prefer classes after 10am, want Fridays free, and care more about a supportive professor than an easy A…" />
            </Field>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field label="Provider"><Select value={provider} onChange={(event) => changeProvider(event.target.value as ModelProvider)}><option value="openai">OpenAI</option><option value="anthropic">Anthropic Claude</option><option value="openai_compatible">Custom / local model</option></Select></Field>
              <Field label={provider === 'anthropic' ? 'Anthropic API key' : provider === 'openai' ? 'OpenAI API key' : 'API key'} optional={provider === 'openai_compatible'}><div className="relative"><KeyRound className="pointer-events-none absolute left-3.5 top-3.5 size-4 text-slate-400" /><Input className="pl-10" type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={provider === 'openai_compatible' ? 'Leave blank for a local server' : 'Used for this request only'} /></div></Field>
              <Field label="Model"><Input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="Model name" /></Field>
              <Field label={provider === 'anthropic' ? 'Anthropic base URL' : provider === 'openai' ? 'OpenAI base URL' : 'OpenAI-compatible base URL'}><Input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder={provider === 'openai_compatible' ? 'http://host.docker.internal:11434/v1' : 'https://…'} /></Field>
            </div>
            {(status || error) && <p role={error ? 'alert' : 'status'} className={`mt-4 text-sm font-semibold ${error ? 'text-red-700' : 'text-emerald-700'}`}>{error || status}</p>}
            <Button className="mt-5" type="button" variant="secondary" onClick={submit} disabled={loading || (provider !== 'openai_compatible' && !apiKey) || !description.trim() || !baseUrl || !modelName}><WandSparkles /> {loading ? 'Preparing suggestion…' : 'Translate preferences'}</Button>
            {result && (
              <Card className="mt-6 border-ucla-blue/20 bg-white"><CardContent className="space-y-5 pt-6">
                <div><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-base font-extrabold text-slate-950">Review before applying</h3><Badge variant="warning">Explicit approval required</Badge></div><p className="mt-1 text-sm leading-6 text-slate-600">The deterministic planner still owns every authoritative fact and score. This proposal only edits the preference inputs shown below.</p></div>
                <div className="grid gap-4 md:grid-cols-2"><div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="mb-2 text-xs font-black uppercase tracking-[.14em] text-slate-500">Current inputs</p><div className="space-y-1 text-sm leading-6 text-slate-700">{proposalLines(contextToProposal(context)).map((line) => <p key={line}>{line}</p>)}</div></div><div className="rounded-xl border border-ucla-blue/20 bg-ucla-blue-soft/45 p-4"><p className="mb-2 text-xs font-black uppercase tracking-[.14em] text-ucla-blue">Suggested inputs</p><div className="space-y-1 text-sm leading-6 text-slate-800">{proposalLines(result.proposal).map((line) => <p key={line}>{line}</p>)}</div></div></div>
                {(result.explanations.length > 0 || result.warnings.length > 0) && <div className="space-y-2 text-sm leading-6 text-slate-700">{result.explanations.map((item) => <p key={item}>• {item}</p>)}{result.warnings.map((item) => <p key={item} className="text-amber-800">⚠ {item}</p>)}</div>}
                <Button type="button" onClick={() => onApply(result.proposal)}>Apply suggestions</Button>
              </CardContent></Card>
            )}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}

function contextToProposal(context: EnhancementContext): EnhancementProposal {
  return { terms: context.terms, format_preference: context.format_preference, hard_constraints: context.hard_constraints, ranking_weights: context.ranking_weights }
}
