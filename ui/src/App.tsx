import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { SessionProvider } from './lib/session'

// Two lazy chunks: the landing page (with the GSAP + Lenis motion stack) and the signed-in
// workspace (framer-motion, Recharts, the app screens and their CSS). Neither loads the other.
const Landing = lazy(() => import('./landing/Landing'))
const Workspace = lazy(() => import('./Workspace'))

const loading = <div className="rm-loading" aria-label="Loading Return Manager" />

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Suspense fallback={loading}>
          <Routes>
            {/* When first clicking the project link (/), it takes the user to /overview */}
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<Landing />} />
            {/* Protected workspace routes */}
            <Route path="/*" element={<Workspace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </SessionProvider>
  )
}
