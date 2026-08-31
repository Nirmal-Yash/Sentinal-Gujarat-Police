import React,{createContext,useContext,useState}from'react'
const C=createContext(null)
export function SidebarProvider({children,defaultOpen=true,onOpenChange}){const[open,setOpen]=useState(defaultOpen);const toggle=()=>setOpen(v=>{const n=!v;onOpenChange?.(n);return n});return <C.Provider value={{open,toggle}}>{children}</C.Provider>}
export function useSidebar(){const v=useContext(C);if(!v)throw Error('useSidebar must be used within SidebarProvider');return v}
export function Sidebar({children}){return <aside data-state={useSidebar().open?'expanded':'collapsed'} className="ui-sidebar">{children}</aside>}
export function SidebarHeader({children}){const child=React.Children.only(children);return <div className="ui-sidebar-header">{React.cloneElement(child,{style:{display:'flex',alignItems:'center',gap:9,width:'100%',...(child.props.style||{})}})}</div>}
export function SidebarContent({children}){return <div className="ui-sidebar-content">{children}</div>}
export function SidebarFooter({children}){return <div className="ui-sidebar-footer">{children}</div>}
export function SidebarGroup({children}){return <section className="ui-sidebar-group">{children}</section>}
export function SidebarGroupLabel({children}){return <div className="ui-sidebar-group-label" style={{padding:'0 9px 8px',color:'#b9aa98',fontSize:11,fontWeight:850,textTransform:'uppercase',letterSpacing:'1.1px',lineHeight:1.2,textShadow:'0 1px 10px rgba(0,0,0,.4)'}}>{children}</div>}
export function SidebarGroupContent({children}){return <div className="ui-sidebar-group-content">{children}</div>}
export function SidebarMenu({children}){return <nav className="ui-sidebar-menu">{children}</nav>}
export function SidebarMenuItem({children}){return <div className="ui-sidebar-menu-item">{children}</div>}
export function SidebarMenuButton({active=false,tooltip,children,onClick,href='#',title,...props}){return <a href={href} onClick={onClick} title={title||tooltip} aria-current={active?'page':undefined} className={`ui-sidebar-menu-button ${active?'is-active':''}`} {...props}>{children}</a>}
export function SidebarTrigger({className=''}){const{toggle,open}=useSidebar();return <button type="button" className={`ui-icon-button ${className}`.trim()} onClick={toggle} aria-label={open?'Collapse navigation sidebar':'Expand navigation sidebar'} title={open?'Collapse navigation':'Expand navigation'}>{open?<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m15 18-6-6 6-6"/></svg>:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m9 18 6-6-6-6"/></svg>}</button>}
