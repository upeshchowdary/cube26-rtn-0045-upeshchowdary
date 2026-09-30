import { useEffect, useState } from 'react'
import { CheckCircle2, CircleAlert, Database, KeyRound, LogOut, Trash2, Users } from 'lucide-react'
import { ApiError, createApiKey, getApiKey, getSystemControls, putSystemControl, revokeApiKey } from '../lib/api'
import { useSession } from '../lib/session'
import { useBatchStore } from '../lib/store'
import type { ControlOut } from '../lib/types'
import { titleCase } from '../lib/format'
import { Header, InlineError } from './shared'

const SCOPES = ['returns:write', 'returns:read', 'review:write', 'evidence:read', 'metrics:read', 'admin']

function ControlsPanel() {
  const [controls, setControls] = useState<ControlOut[] | null>(null)
  const [error, setError] = useState('')
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const load = () => {
    setError('')
    getSystemControls()
      .then((res) => setControls(res.controls))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load system controls.'))
  }

  useEffect(load, [])

  const toggle = async (control: ControlOut) => {
    const reason = reasons[control.control]?.trim()
    if (!reason) {
      setError(`Give a reason before changing "${control.control}".`)
      return
    }
    setSaving(control.control)
    setError('')
    try {
      const res = await putSystemControl({ control: control.control, enabled: !control.enabled, reason })
      setControls(res.controls)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update this control.')
    } finally {
      setSaving(null)
    }
  }

  if (error && !controls) return <InlineError><CircleAlert size={14} /> {error}</InlineError>
  if (!controls) return <div className="no-data-note">Loading system controls...</div>

  return (
    <div className="controls-list">
      {error && <InlineError><CircleAlert size={14} /> {error}</InlineError>}
      {controls.map((c) => (
        <div className="control-row" key={c.control}>
          <div>
            <b>{titleCase(c.control)}</b>
            <small>
              {c.enabled ? 'Enabled' : 'Disabled'}
              {c.reason ? ` · ${c.reason}` : ''}
              {c.updated_by ? ` · by ${c.updated_by}` : ''}
            </small>
          </div>
          <label className="field" style={{ minWidth: 180 }}>
            <input
              placeholder="Reason (required)"
              value={reasons[c.control] ?? ''}
              onChange={(e) => setReasons((prev) => ({ ...prev, [c.control]: e.target.value }))}
            />
          </label>
          <button className={`button ${c.enabled ? 'primary' : ''}`} disabled={saving === c.control} onClick={() => void toggle(c)}>
            {saving === c.control ? 'Saving...' : c.enabled ? 'Turn off' : 'Turn on'}
          </button>
        </div>
      ))}
    </div>
  )
}

function ApiKeysPanel() {
  const [name, setName] = useState('')
  const [scopes, setScopes] = useState<string[]>(['returns:write', 'returns:read'])
  const [created, setCreated] = useState<{ api_key: string; key_id: string } | null>(null)
  const [error, setError] = useState('')
  const [revokeId, setRevokeId] = useState('')
  const [revokeMsg, setRevokeMsg] = useState('')

  const toggleScope = (scope: string) => {
    setScopes((prev) => (prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]))
  }

  const create = async () => {
    if (!name.trim() || scopes.length === 0) {
      setError('Give the key a name and at least one scope.')
      return
    }
    setError('')
    try {
      const res = await createApiKey({ name: name.trim(), scopes })
      setCreated(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the key.')
    }
  }

  const revoke = async () => {
    if (!revokeId.trim()) return
    setRevokeMsg('')
    try {
      await revokeApiKey(revokeId.trim())
      setRevokeMsg(`Revoked ${revokeId.trim()}.`)
      setRevokeId('')
    } catch (err) {
      setRevokeMsg(err instanceof ApiError ? err.message : 'Could not revoke that key.')
    }
  }

  return (
    <div className="controls-list">
      <label className="field">
        <span>New key name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="recovery-pod, ui-dev, ..." />
      </label>
      <div className="toggle-row" style={{ flexWrap: 'wrap', gap: 8 }}>
        {SCOPES.map((s) => (
          <button key={s} className={`tab ${scopes.includes(s) ? 'selected' : ''}`} onClick={() => toggleScope(s)} type="button">
            {s}
          </button>
        ))}
      </div>
      {error && <InlineError><CircleAlert size={14} /> {error}</InlineError>}
      <div className="save-row">
        <small>The plaintext key is shown once and cannot be retrieved again.</small>
        <button className="button primary" onClick={() => void create()}>
          <KeyRound size={14} /> Create key
        </button>
      </div>
      {created && (
        <div className="upload-notes">
          <span>
            <b>{created.key_id}</b>
          </span>
          <span>
            <code>{created.api_key}</code>
          </span>
        </div>
      )}
      <label className="field">
        <span>Revoke a key by id</span>
        <input value={revokeId} onChange={(e) => setRevokeId(e.target.value)} placeholder="key id" />
      </label>
      <div className="dialog-actions">
        <button className="button" onClick={() => void revoke()}>
          Revoke
        </button>
      </div>
      {revokeMsg && <small>{revokeMsg}</small>}
    </div>
  )
}

function CachePanel() {
  const { jobs, rows, clearCache } = useBatchStore()
  const [clearing, setClearing] = useState(false)
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleClear = async () => {
    setClearing(true)
    setStatusMsg(null)
    try {
      await clearCache()
      setStatusMsg({
        type: 'success',
        text: 'All cache data (in-memory state, inspection caches, browser storage, and server-side batch jobs) have been erased and cleaned.',
      })
    } catch {
      setStatusMsg({
        type: 'error',
        text: 'An error occurred while attempting to clear cache data.',
      })
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="controls-list">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px', margin: '10px 0 16px' }}>
        <div style={{ padding: '12px', background: 'var(--canvas)', borderRadius: '8px', border: '1px solid var(--line)' }}>
          <small style={{ color: 'var(--muted)', fontSize: '9.5px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '5px' }}>
            <Database size={12} /> Stored Batch Jobs
          </small>
          <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '6px' }}>{jobs.length}</div>
          <small style={{ color: 'var(--muted)', fontSize: '9px', marginTop: '4px', display: 'block' }}>Job folders & output artifacts</small>
        </div>
        <div style={{ padding: '12px', background: 'var(--canvas)', borderRadius: '8px', border: '1px solid var(--line)' }}>
          <small style={{ color: 'var(--muted)', fontSize: '9.5px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '5px' }}>
            <Database size={12} /> Cached Return Records
          </small>
          <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '6px' }}>{rows.length}</div>
          <small style={{ color: 'var(--muted)', fontSize: '9px', marginTop: '4px', display: 'block' }}>In-memory evaluated items</small>
        </div>
        <div style={{ padding: '12px', background: 'var(--canvas)', borderRadius: '8px', border: '1px solid var(--line)' }}>
          <small style={{ color: 'var(--muted)', fontSize: '9.5px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '5px' }}>
            <CheckCircle2 size={12} color="#2563eb" /> Where it is held
          </small>
          <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '10px', color: 'var(--blue)' }}>This browser tab</div>
          <small style={{ color: 'var(--muted)', fontSize: '9px', marginTop: '4px', display: 'block' }}>Reloading the page fetches the rows from the API again</small>
        </div>
      </div>

      <div style={{ padding: '16px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.06)', border: '1px solid rgba(239, 68, 68, 0.25)', margin: '8px 0 16px' }}>
        <b style={{ color: 'var(--danger)', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Trash2 size={15} /> Erase All Stored Cache Data
        </b>
        <p style={{ margin: '8px 0 14px', fontSize: '11px', color: 'var(--muted)', lineHeight: '1.6' }}>
          Clearing the cache permanently cleans all stored and temporary data:
        </p>
        <ul style={{ margin: '0 0 16px 18px', padding: 0, fontSize: '10px', color: 'var(--muted)', lineHeight: '1.7' }}>
          <li>In-memory inspection detail caches and review decision histories</li>
          <li>Browser session and temporary local storage</li>
          <li>Server-side uploaded batch jobs, outputs, and generated analysis files</li>
        </ul>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <button
            className="button"
            onClick={() => void handleClear()}
            disabled={clearing}
            style={{
              background: '#dc2626',
              borderColor: '#b91c1c',
              color: '#ffffff',
              fontWeight: 600,
              padding: '0 16px',
              boxShadow: '0 2px 8px rgba(220, 38, 38, 0.3)',
            }}
          >
            <Trash2 size={14} /> {clearing ? 'Erasing and cleaning cache...' : 'Clear All Cache Data'}
          </button>
          <small style={{ color: 'var(--muted)', fontSize: '9.5px' }}>
            Your API authentication key will remain saved so you stay signed in.
          </small>
        </div>
      </div>

      {statusMsg && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 14px',
            borderRadius: '6px',
            background: statusMsg.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
            border: `1px solid ${statusMsg.type === 'success' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
            color: statusMsg.type === 'success' ? 'var(--success)' : 'var(--danger)',
            fontSize: '11px',
            fontWeight: 500,
          }}
        >
          {statusMsg.type === 'success' ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}
          <span>{statusMsg.text}</span>
        </div>
      )}
    </div>
  )
}

export default function SettingsPage() {
  const [tab, setTab] = useState('System controls')
  const { disconnect } = useSession()
  const { clearCache } = useBatchStore()
  const [footerClearing, setFooterClearing] = useState(false)
  const [footerMsg, setFooterMsg] = useState('')
  const tabs = ['System controls', 'API keys', 'Data & cache', 'Users & roles', 'Appearance']
  const key = getApiKey() ?? ''

  const handleFooterClear = async () => {
    setFooterClearing(true)
    setFooterMsg('')
    try {
      await clearCache()
      setFooterMsg('Cache erased successfully!')
      setTimeout(() => setFooterMsg(''), 4000)
    } catch {
      setFooterMsg('Failed to clear cache.')
      setTimeout(() => setFooterMsg(''), 4000)
    } finally {
      setFooterClearing(false)
    }
  }

  return (
    <>
      <Header eyebrow="CONFIGURATION / WORKSPACE" title="Settings" subtitle="Manage the real backend's kill switches, API credentials, and cache storage." />
      <div className="settings-layout">
        <nav>
          {tabs.map((t) => (
            <button className={tab === t ? 'chosen' : ''} key={t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        <section className="panel settings-panel">
          <div className="panel-head">
            <div>
              <h2>{tab}</h2>
              <p>
                {tab === 'System controls'
                  ? 'These are the real §6.7 kill switches - flipping one changes worker behavior immediately.'
                  : tab === 'API keys'
                    ? 'Create and revoke real, scoped API keys against this org.'
                    : tab === 'Data & cache'
                      ? 'Erase stored return jobs, inspection details, and local browser cache.'
                      : tab === 'Users & roles'
                        ? 'UI visibility is not a substitute for backend authorization.'
                        : 'Local to this browser.'}
              </p>
            </div>
          </div>
          {tab === 'System controls' && <ControlsPanel />}
          {tab === 'API keys' && <ApiKeysPanel />}
          {tab === 'Data & cache' && <CachePanel />}
          {tab === 'Users & roles' &&
            ['Operator · Create returns, upload batches, accept or override decisions', 'Reviewer · Resolve reviews and give the second-person sign-off', 'Admin · Kill switches, API keys and reference data'].map((r) => (
              <div className="role-row" key={r}>
                <Users size={16} />
                {r}
              </div>
            ))}
          {tab === 'Appearance' && (
            <div className="appearance">
              <button onClick={() => document.querySelector('.shell')?.classList.remove('dark')}>Light</button>
              <button onClick={() => document.querySelector('.shell')?.classList.add('dark')}>Dark</button>
              <button onClick={() => document.querySelector('.shell')?.classList.remove('dark')}>System</button>
            </div>
          )}
          <div className="save-row">
            <small>Connected with key ending in ...{key.slice(-4)}</small>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                className="button"
                onClick={() => void handleFooterClear()}
                disabled={footerClearing}
                title="Erase all stored cache data"
                style={{
                  borderColor: 'rgba(239, 68, 68, 0.45)',
                  color: 'var(--danger)',
                }}
              >
                <Trash2 size={13} /> {footerClearing ? 'Clearing cache...' : 'Clear cache'}
              </button>
              <button className="button" onClick={disconnect}>
                <LogOut size={14} /> Disconnect
              </button>
            </div>
          </div>
          {footerMsg && (
            <div style={{ marginTop: '8px', fontSize: '10.5px', color: 'var(--success)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle2 size={13} /> {footerMsg}
            </div>
          )}
        </section>
      </div>
    </>
  )
}
