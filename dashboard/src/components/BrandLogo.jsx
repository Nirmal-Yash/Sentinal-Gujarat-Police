export default function BrandLogo({ compact = false, className = '', alt = 'Gujarat Police emblem', ...props }) {
  const src = '/gujarat-police-logo-png_seeklogo-611297.png'
  return (
    <img
      src={src}
      alt={alt}
      className={['sentinel-brand-logo', compact ? 'sentinel-brand-logo--compact' : 'sentinel-brand-logo--full', className].filter(Boolean).join(' ')}
      {...props}
      style={{
        display: 'block',
        objectFit: 'cover',
        objectPosition: 'center',
        ...(props.style || {}),
      }}
    />
  )
}
