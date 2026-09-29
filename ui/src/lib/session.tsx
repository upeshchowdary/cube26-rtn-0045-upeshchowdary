import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getApiKey, onUnauthorized, setApiKey as persistApiKey } from './api'

interface SessionState {
  apiKey: string | null
  connected: boolean
  connect: (key: string) => void
  disconnect: () => void
}

const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(() => getApiKey())

  useEffect(() => {
    onUnauthorized(() => setApiKeyState(null))
    return () => onUnauthorized(null)
  }, [])

  const connect = (key: string) => {
    persistApiKey(key)
    setApiKeyState(key)
  }
  const disconnect = () => {
    persistApiKey(null)
    setApiKeyState(null)
  }

  return (
    <SessionContext.Provider value={{ apiKey, connected: !!apiKey, connect, disconnect }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}
