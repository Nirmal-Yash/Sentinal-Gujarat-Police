export function Badge({children,variant='default',className=''}){return <span className={`ui-badge ui-badge-${variant} ${className}`.trim()}>{children}</span>}
