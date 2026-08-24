import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex shrink-0 items-center justify-center gap-2 rounded-xl text-sm font-bold transition-all outline-none focus-visible:ring-3 focus-visible:ring-ucla-gold/45 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4',
  {
    variants: {
      variant: {
        default: 'bg-ucla-blue text-white shadow-sm hover:bg-ucla-blue-dark hover:-translate-y-0.5',
        secondary: 'border border-ucla-blue/15 bg-ucla-blue-soft text-ucla-blue-dark hover:bg-ucla-blue/10',
        outline: 'border border-slate-300 bg-white text-slate-800 hover:border-ucla-blue/35 hover:bg-ucla-blue-soft/60',
        ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
        gold: 'bg-ucla-gold text-slate-950 shadow-sm hover:bg-ucla-gold-dark hover:-translate-y-0.5',
        danger: 'bg-red-50 text-red-700 hover:bg-red-100',
      },
      size: {
        default: 'h-11 px-5',
        sm: 'h-9 rounded-lg px-3 text-xs',
        lg: 'h-13 px-7 text-base',
        icon: 'size-10 p-0',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }

function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />
}

export { Button, buttonVariants }
