import{j as c}from"./jsx-runtime-9bc08dc0.js";import{f as e}from"./index-43965908.js";import{c as U,S as F}from"./store-1448cd49.js";import"./index-f169cc97.js";/**
 * @license lucide-react v0.511.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const H=[["path",{d:"m15 18-6-6 6-6",key:"1wnfg3"}]],J=U("chevron-left",H),K={compact:"px-3 py-1.5 text-xs",small:"px-[11px] py-[6px] text-[12.5px]",control:"px-4 py-2 text-sm",medium:"px-[15px] py-[9px] text-sm",spacious:"px-[18px] py-[11px] text-[15px]",large:"px-[22px] py-3 text-[15px]"},Q={primary:"border border-transparent bg-ink text-ink-on hover:bg-[#383838] dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-[#d8d3c8]",secondary:"border border-ink bg-surface text-fg hover:bg-surface-hover dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark",table:"border border-ink bg-transparent text-fg hover:bg-surface-hover dark:border-ink-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark",muted:"border border-line bg-transparent text-fg-secondary hover:bg-surface-hover dark:border-line-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark",danger:"border border-error text-error hover:bg-error-bg dark:border-error-dark dark:text-error-dark dark:hover:bg-error-bg-dark"};function R({label:_,onClick:D,variant:G="primary",size:V="medium",icon:$,disabled:I=!1,ariaPressed:L,className:O=""}){const P="inline-flex cursor-pointer items-center justify-center gap-2 font-display font-normal tracking-[-0.02em] transition-colors disabled:cursor-not-allowed disabled:opacity-50";return c.jsxs("button",{type:"button",onClick:D,disabled:I,"aria-pressed":L,className:`${P} ${K[V]} rounded-md ${Q[G]} ${O}`,children:[$,_]})}R.__docgenInfo={description:"Button variants based on the actions used throughout the Mattin app template.",methods:[],displayName:"ButtonApp",props:{label:{required:!0,tsType:{name:"string"},description:""},onClick:{required:!1,tsType:{name:"signature",type:"function",raw:"() => void",signature:{arguments:[],return:{name:"void"}}},description:""},variant:{required:!1,tsType:{name:"union",raw:"'primary' | 'secondary' | 'table' | 'muted' | 'danger'",elements:[{name:"literal",value:"'primary'"},{name:"literal",value:"'secondary'"},{name:"literal",value:"'table'"},{name:"literal",value:"'muted'"},{name:"literal",value:"'danger'"}]},description:"",defaultValue:{value:"'primary'",computed:!1}},size:{required:!1,tsType:{name:"union",raw:"'compact' | 'small' | 'control' | 'medium' | 'spacious' | 'large'",elements:[{name:"literal",value:"'compact'"},{name:"literal",value:"'small'"},{name:"literal",value:"'control'"},{name:"literal",value:"'medium'"},{name:"literal",value:"'spacious'"},{name:"literal",value:"'large'"}]},description:"",defaultValue:{value:"'medium'",computed:!1}},icon:{required:!1,tsType:{name:"ReactNode"},description:""},disabled:{required:!1,tsType:{name:"boolean"},description:"",defaultValue:{value:"false",computed:!1}},ariaPressed:{required:!1,tsType:{name:"boolean"},description:""},className:{required:!1,tsType:{name:"string"},description:"",defaultValue:{value:"''",computed:!1}}}};const ee={title:"UI/ButtonApp",component:R,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{variant:{control:"select"},size:{control:"select"}}},r={args:{label:"My Apps",variant:"secondary",size:"medium",icon:c.jsx(J,{className:"h-[14px] w-[14px]","aria-hidden":"true"}),onClick:e()}},a={args:{label:"+ Nuevo agente",variant:"primary",size:"spacious",onClick:e()}},s={args:{label:"Abrir",variant:"table",size:"small",onClick:e()}},t={args:{label:"Editar",variant:"muted",size:"small",onClick:e()}},n={args:{label:"Reintentar",variant:"danger",size:"compact",onClick:e()}},o={args:{label:"+ Conectar",variant:"secondary",size:"medium",onClick:e()}},i={args:{label:"Guardar cambios",variant:"primary",size:"large",onClick:e()}},l={args:{label:"Browse Agents",variant:"primary",size:"spacious",icon:c.jsx(F,{className:"h-4 w-4","aria-hidden":"true"}),onClick:e()}};var d,p,m;r.parameters={...r.parameters,docs:{...(d=r.parameters)==null?void 0:d.docs,source:{originalSource:`{
  args: {
    label: 'My Apps',
    variant: 'secondary',
    size: 'medium',
    icon: <ChevronLeft className="h-[14px] w-[14px]" aria-hidden="true" />,
    onClick: fn()
  }
}`,...(m=(p=r.parameters)==null?void 0:p.docs)==null?void 0:m.source}}};var u,g,b;a.parameters={...a.parameters,docs:{...(u=a.parameters)==null?void 0:u.docs,source:{originalSource:`{
  args: {
    label: '+ Nuevo agente',
    variant: 'primary',
    size: 'spacious',
    onClick: fn()
  }
}`,...(b=(g=a.parameters)==null?void 0:g.docs)==null?void 0:b.source}}};var v,k,f;s.parameters={...s.parameters,docs:{...(v=s.parameters)==null?void 0:v.docs,source:{originalSource:`{
  args: {
    label: 'Abrir',
    variant: 'table',
    size: 'small',
    onClick: fn()
  }
}`,...(f=(k=s.parameters)==null?void 0:k.docs)==null?void 0:f.source}}};var y,x,h;t.parameters={...t.parameters,docs:{...(y=t.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    label: 'Editar',
    variant: 'muted',
    size: 'small',
    onClick: fn()
  }
}`,...(h=(x=t.parameters)==null?void 0:x.docs)==null?void 0:h.source}}};var C,A,z;n.parameters={...n.parameters,docs:{...(C=n.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    label: 'Reintentar',
    variant: 'danger',
    size: 'compact',
    onClick: fn()
  }
}`,...(z=(A=n.parameters)==null?void 0:A.docs)==null?void 0:z.source}}};var S,w,N;o.parameters={...o.parameters,docs:{...(S=o.parameters)==null?void 0:S.docs,source:{originalSource:`{
  args: {
    label: '+ Conectar',
    variant: 'secondary',
    size: 'medium',
    onClick: fn()
  }
}`,...(N=(w=o.parameters)==null?void 0:w.docs)==null?void 0:N.source}}};var M,T,q;i.parameters={...i.parameters,docs:{...(M=i.parameters)==null?void 0:M.docs,source:{originalSource:`{
  args: {
    label: 'Guardar cambios',
    variant: 'primary',
    size: 'large',
    onClick: fn()
  }
}`,...(q=(T=i.parameters)==null?void 0:T.docs)==null?void 0:q.source}}};var B,j,E;l.parameters={...l.parameters,docs:{...(B=l.parameters)==null?void 0:B.docs,source:{originalSource:`{
  args: {
    label: 'Browse Agents',
    variant: 'primary',
    size: 'spacious',
    icon: <Store className="h-4 w-4" aria-hidden="true" />,
    onClick: fn()
  }
}`,...(E=(j=l.parameters)==null?void 0:j.docs)==null?void 0:E.source}}};const re=["DashboardMyApps","AgentsNewAgent","AgentsOpen","AgentsEdit","DataSourcesRetry","McpServerConnect","GeneralSettingsSave","MarketplaceBrowseAgents"];export{t as AgentsEdit,a as AgentsNewAgent,s as AgentsOpen,r as DashboardMyApps,n as DataSourcesRetry,i as GeneralSettingsSave,l as MarketplaceBrowseAgents,o as McpServerConnect,re as __namedExportsOrder,ee as default};
