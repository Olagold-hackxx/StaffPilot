"use client"

import type React from "react"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { DashboardHeader } from "@/components/dashboard/dashboard-header"
import { DashboardSidebar } from "@/components/dashboard/dashboard-sidebar"
import { authService } from "@/lib/auth"
import { Loader2 } from "lucide-react"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const [isChecking, setIsChecking] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    async function checkAuth() {
      const authenticated = authService.isAuthenticated()
      
      if (!authenticated) {
        router.push("/login")
        return
      }

      // Verify token is still valid
      try {
        const user = await authService.getCurrentUser()
        if (!user) {
          router.push("/login")
          return
        }
        setIsAuthenticated(true)
      } catch (error: unknown) {
        // Token invalid or expired, redirect to login
        router.push("/login")
        return
      } finally {
        setIsChecking(false)
      }
    }

    checkAuth()
  }, [router])

  if (isChecking) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null // Will redirect to login
  }

  return (
    <div className="flex min-h-screen">
      <DashboardSidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <DashboardHeader />
        <main className="flex-1 p-6 lg:p-8 bg-muted/30">{children}</main>
      </div>
    </div>
  )
}
