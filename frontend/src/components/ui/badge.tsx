import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-extrabold tracking-wide', {
  variants: {
    variant: {
      default: 'bg-ucla-blue-soft text-ucla-blue-dark',
      success: 'bg-emerald-50 text-emerald-700',
      warning: 'bg-amber-50 text-amber-800',
      danger: 'bg-red-50 text-red-700',
      outline: 'border border-slate-200 bg-white text-slate-600',
      gold: 'bg-ucla-gold/20 text-amber-900',
    },
  },
  defaultVariants: { variant: 'default' },
})

type BadgeProps = React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge }
