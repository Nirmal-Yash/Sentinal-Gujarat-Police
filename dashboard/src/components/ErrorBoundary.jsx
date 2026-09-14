import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an unhandled error:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
    if (this.props.onReset) {
      this.props.onReset()
    } else {
      window.location.href = '/feeds'
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          width: '100%',
          padding: 24,
          background: 'var(--bg, #000)',
          color: 'var(--text, #fff)',
          textAlign: 'center'
        }}>
          <div style={{
            maxWidth: 520,
            padding: '24px 28px',
            borderRadius: 12,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            boxShadow: 'var(--shadow)'
          }}>
            <h2 style={{ margin: '0 0 10px', fontSize: 18, color: 'var(--accent)' }}>
              {this.props.title || 'View temporarily unavailable'}
            </h2>
            <p style={{ margin: '0 0 18px', fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>
              {this.state.error?.message || 'An unexpected error occurred while rendering this view.'}
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button
                type="button"
                onClick={this.handleReset}
                style={{
                  padding: '8px 18px',
                  borderRadius: 7,
                  border: '1px solid var(--accent)',
                  background: 'var(--accent)',
                  color: 'var(--on-accent)',
                  fontSize: 12,
                  fontWeight: 800,
                  cursor: 'pointer'
                }}
              >
                Return to Monitor
              </button>
              <button
                type="button"
                onClick={() => this.setState({ hasError: false, error: null })}
                style={{
                  padding: '8px 18px',
                  borderRadius: 7,
                  border: '1px solid var(--border)',
                  background: 'var(--surface2)',
                  color: 'var(--text)',
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: 'pointer'
                }}
              >
                Retry View
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
