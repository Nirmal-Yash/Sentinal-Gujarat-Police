import React from 'react'

export function Button({ asChild=false, variant='default', size='default', className='', children, ...props }) {
  const tag = asChild ? 'span' : 'button'
  return React.createElement(tag, {
    className: `ui-button ui-button-${variant} ui-button-${size} ${className}`.trim(),
    ...props,
  }, children)
}
