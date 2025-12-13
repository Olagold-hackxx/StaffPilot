"use client"

import type React from "react"

import { createContext, useContext, useEffect, useState, useMemo } from "react"

type Theme = "dark" | "light"

type ThemeProviderProps = {
  readonly children: React.ReactNode
  readonly defaultTheme?: Theme
}

type ThemeProviderState = {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const ThemeProviderContext = createContext<ThemeProviderState | undefined>(undefined)

const THEME_STORAGE_KEY = "staffpilot-theme"

export function ThemeProvider({ children }: ThemeProviderProps) {
  // Always use dark theme, no state management needed
  useEffect(() => {
    // Always apply dark theme
    const root = globalThis.document.documentElement
    root.classList.remove("light", "dark")
    root.classList.add("dark")
  }, [])

  // Provide a no-op setTheme function for compatibility
  const value = useMemo(() => ({ 
    theme: "dark" as Theme, 
    setTheme: () => {} // No-op function
  }), [])

  return <ThemeProviderContext.Provider value={value}>{children}</ThemeProviderContext.Provider>
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext)
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }
  return context
}
