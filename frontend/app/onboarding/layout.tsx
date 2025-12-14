"use client"

import { usePathname } from "next/navigation"
import { Check, ArrowRight } from "lucide-react"
import { Progress } from "@/components/ui/progress"

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()

  const steps = [
    {
      id: "business-details",
      name: "Business Details",
      path: "/onboarding/business-details",
    },
    {
      id: "integrations",
      name: "Integrations",
      path: "/onboarding/integrations",
    },
  ]

  const currentStepIndex = steps.findIndex((step) => pathname.includes(step.id))
  const progress = ((currentStepIndex + 1) / steps.length) * 100

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="mx-auto max-w-4xl px-4 py-8">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Welcome to StaffPilot
          </h1>
          <p className="mt-2 text-slate-600 dark:text-slate-400">
            Let's get your workspace ready for action
          </p>
        </div>

        {/* Progress Stepper */}
        <div className="mb-12">
          <div className="relative flex justify-between">
            {steps.map((step, index) => {
              const isCompleted = index < currentStepIndex
              const isCurrent = index === currentStepIndex

              return (
                <div key={step.id} className="flex flex-col items-center relative z-10 w-full">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all duration-200 ${
                      isCompleted || isCurrent
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-slate-300 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-900"
                    }`}
                  >
                    {isCompleted ? (
                      <Check className="h-6 w-6" />
                    ) : (
                      <span className="text-sm font-semibold">{index + 1}</span>
                    )}
                  </div>
                  <span
                    className={`mt-2 text-sm font-medium transition-colors duration-200 ${
                      isCompleted || isCurrent
                        ? "text-primary"
                        : "text-slate-500 dark:text-slate-400"
                    }`}
                  >
                    {step.name}
                  </span>
                </div>
              )
            })}
            
            {/* Connecting Lines */}
            <div className="absolute top-5 left-0 -z-0 h-[2px] w-full bg-slate-200 dark:bg-slate-800">
               <div 
                className="h-full bg-primary transition-all duration-500 ease-in-out"
                style={{ width: `${Math.max(0, currentStepIndex / (steps.length - 1) * 100)}%` }}
               />
            </div>
            
          </div>
        </div>

        {/* Content */}
        <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          {children}
        </div>
      </div>
    </div>
  )
}
