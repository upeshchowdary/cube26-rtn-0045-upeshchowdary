import { useState } from 'react'
import { CircleAlert, KeyRound, ShieldCheck } from 'lucide-react'
import { motion } from 'framer-motion'
import { ApiError, listBatchJobs, setApiKey } from './lib/api'
import { useSession } from './lib/session'

const PREFILLED_KEY = (import.meta.env.VITE_API_KEY as string | undefined) || ''

export default function Connect() {
  const { connect } = useSession()
  const [key, setKey] = useState(PREFILLED_KEY)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    const trimmed = key.trim()
    if (!trimmed) {
      setError('Enter an API key.')
      return
    }
    setChecking(true)
    setError('')
    setApiKey(trimmed)
    try {
      await listBatchJobs()
      connect(trimmed)
    } catch (err) {
      setApiKey(null)
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? err.message
            : `The backend rejected this key (${err.status}): ${err.detail ?? err.message}`
          : 'Could not verify this key.',
      )
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="overlay connect-screen">
      <motion.div className="dialog connect-dialog" initial={{ y: 12, scale: 0.98, opacity: 0 }} animate={{ y: 0, scale: 1, opacity: 1 }}>
        <div className="dialog-head">
          <div>
            <small>RETURN MANAGER</small>
            <h2>Connect to the backend</h2>
          </div>
          <span className="float-icon green">
            <KeyRound size={17} />
          </span>
        </div>
        <p>
          This workspace reads and writes real data through the Returns Manager API. Enter an API
          key created with <code>returns-manager keys create</code>.
        </p>
        <label className="field">
          <span>API key</span>
          <input
            autoFocus
            value={key}
            onChange={(event) => setKey(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && void submit()}
            placeholder="rmk_local_..."
            spellCheck={false}
          />
        </label>
        {error && (
          <div className="connect-error">
            <CircleAlert size={14} /> {error}
          </div>
        )}
        <div className="dialog-actions">
          <button className="button primary" disabled={checking} onClick={() => void submit()}>
            {checking ? 'Checking...' : 'Connect'}
          </button>
        </div>
        <div className="connect-footnote">
          <ShieldCheck size={13} /> Stored only in this browser's local storage, sent as
          <code>X-API-Key</code> on every request.
        </div>
      </motion.div>
    </div>
  )
}
