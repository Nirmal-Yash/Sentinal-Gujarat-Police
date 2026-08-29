import React from 'react'

export const Input = React.forwardRef(function Input({ className='', ...props }, ref) {
  return <input ref={ref} className={`ui-input ${className}`.trim()} {...props} />
})
