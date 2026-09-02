export default function BrandLogo({ compact = false, className = '', alt = 'Sentinel AI — Gujarat Police Operations', ...props }) {
  const src = '/gujarat-police-logo-png_seeklogo-611297.png'
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
