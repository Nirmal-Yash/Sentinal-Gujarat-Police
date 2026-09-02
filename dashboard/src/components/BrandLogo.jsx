export default function BrandLogo({ compact = false, className = '', alt = 'Sentinel AI — Gujarat Police Operations', ...props }) {
  const src = compact ? '/sentinel-logo-mark.svg' : '/sentinel-logo.svg'
  return (
    <img
      src={src}
      alt={alt}
      className={['sentinel-brand-logo', compact ? 'sentinel-brand-logo--compact' : 'sentinel-brand-logo--full', className].filter(Boolean).join(' ')}
      {...props}
      style={{
        display: 'block',
        width: '100%',
        height: 'auto',
        objectFit: 'contain',
        objectPosition: 'center',
        ...(props.style || {}),
      }}
    />
  )
}
