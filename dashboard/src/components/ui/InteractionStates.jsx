import React from 'react'

export function Skeleton({ className = '', width = '100%', height = 12, style = {} }) {
  return <span aria-hidden="true" className={`sentinel-skeleton ${className}`} style={{ width, height, ...style }} />
}

export function SuccessCheck({ label = 'Success' }) {
  return <span className="sentinel-success-check" role="status" aria-label={label}>✓</span>
}

export function EmptyState({ icon = '◌', title, description, action }) {
  return <div className="sentinel-empty-state" role="status">
    <div className="sentinel-empty-icon" aria-hidden="true">{icon}</div>
    {title && <strong>{title}</strong>}
    {description && <span>{description}</span>}
    {action && <div className="sentinel-empty-action">{action}</div>}
  </div>
}

export function FormError({ children }) {
  return <div className="sentinel-form-error" role="alert">{children}</div>
}
