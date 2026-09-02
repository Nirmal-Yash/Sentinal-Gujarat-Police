import { useState } from 'react'
import BrandLogo from './BrandLogo'

export default function LoginModal({ onLogin, error: externalError = '' }) {
  const [username, setUsername] = useState(''), [password, setPassword] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const submit = async event => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await onLogin({ username, password })
      const target = '/feeds'
      if (window.location.pathname !== target) {
        window.history.replaceState({ ...window.history.state, sentinelRoute: target }, '', target)
        window.dispatchEvent(new PopStateEvent('popstate'))
      }
    } catch (err) {
      setError(err?.message || 'Invalid username or password')
    } finally {
      setBusy(false)
    }
  }
  return <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg)', color: 'var(--text)' }}><form onSubmit={submit} style={{ width: 340, padding: 24, borderRadius: 10, background: 'var(--surface)', border: '1px solid var(--border)', color:'var(--text)' }}><div style={{display:'grid',justifyItems:'center',gap:8,marginBottom:14}}><BrandLogo alt="Sentinel AI — Gujarat Police Operations" style={{ width: '100%', maxWidth: 260, height: 'auto' }} /><span style={{color:'var(--text2)',fontSize:10,letterSpacing:'.7px',textTransform:'uppercase'}}>Authorized operator access</span></div>{externalError && <p style={{ color: 'var(--red)', fontSize: 12, marginBottom: 10 }}>Authentication service unavailable. Verify the API service and environment configuration.</p>}<label style={label}>Username<input value={username} onChange={event => setUsername(event.target.value)} required autoFocus style={input}/></label><label style={label}>Password<input value={password} onChange={event => setPassword(event.target.value)} type="password" required style={input}/></label>{error && <p style={{ color: 'var(--red)', fontSize: 12 }}>{error}</p>}<button disabled={busy} style={{...button,opacity:busy?.65:1,cursor:busy?'default':'pointer'}}>{busy ? 'Signing in…' : 'Sign in'}</button></form></main>
}
const label = { display: 'grid', gap: 5, marginTop: 12, fontSize: 12, color: 'var(--text2)' }
const input = { padding: '8px 10px', borderRadius: 5, border: '1px solid var(--border)', background: 'var(--surface2)', color: 'var(--text)' }
const button = { width: '100%', marginTop: 18, padding: '9px', border: 0, borderRadius: 5, background: 'var(--accent)', color: '#fff' }
