import{j as e}from"./jsx-runtime-9bc08dc0.js";import{f as r}from"./index-43965908.js";function X(n,t){!t||n.key!=="Enter"&&n.key!==" "||(n.preventDefault(),t())}function U(n,t){n.stopPropagation(),t==null||t()}function H({title:n,description:t,badges:y=[],table:s,metadata:p,topRight:k,imageSrc:v,imageAlt:M="",badgeText:K,onClick:g,actionLabel:x,onActionClick:F,actionDisabled:G=!1,className:_=""}){const f=!!g;return e.jsxs("button",{className:`group flex h-full flex-col rounded-md bg-surface-ash p-5 text-left  ${f?"cursor-pointer":""} ${_}`,role:f?"button":void 0,tabIndex:f?0:void 0,onClick:g,onKeyDown:a=>X(a,g),children:[e.jsxs("div",{className:"mb-3 flex items-start justify-between gap-3",children:[e.jsx("div",{className:"flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden rounded-md border-[0.8px] border-[#FF682C] text-sm font-medium ",children:v?e.jsx("img",{src:v,alt:M,className:"h-full w-full object-cover"}):K}),k&&e.jsx("div",{className:"min-w-0",children:k})]}),e.jsx("h3",{className:"mb-1 font-display text-lg font-normal tracking-[-0.02em] text-ink dark:text-ink-dark",children:n}),t&&e.jsx("p",{className:"mb-4 text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark",children:t}),y.length>0&&e.jsx("div",{className:"mb-4 flex flex-wrap gap-2",children:y.map(a=>e.jsx("span",{className:`rounded-full px-2.5 py-1 text-xs font-medium ${a.className??""}`,style:{...a.color?{backgroundColor:a.color,color:"#ffffff"}:{}},children:a.text},a.text))}),s!==void 0?e.jsx("div",{className:"mt-auto overflow-x-auto border-t border-[#e0ddd6] pt-2 dark:border-line-dark",children:e.jsxs("table",{className:"table-fixed text-center leading-none",children:[e.jsx("thead",{children:e.jsx("tr",{children:s.map((a,b)=>e.jsx("th",{className:`px-2 py-0 text-[8px] font-medium uppercase tracking-[0.04em] text-fg-tertiary dark:text-fg-tertiary-dark ${b<s.length-1?"border-r border-[#e0ddd6] dark:border-line-dark":""}`,children:a.label},`label-${a.label}`))})}),e.jsx("tbody",{children:e.jsx("tr",{children:s.map((a,b)=>e.jsx("td",{className:`px-2 py-0 text-sm font-semibold text-ink dark:text-ink-dark ${b<s.length-1?"border-r border-[#e0ddd6] dark:border-line-dark":""}`,children:a.value},`value-${a.label}`))})})]})}):(p||x)&&e.jsxs("div",{className:"mt-auto flex items-center gap-3 border-t border-[#e0ddd6] pt-3 text-xs text-fg-tertiary dark:border-line-dark dark:text-fg-tertiary-dark",children:[p&&e.jsx("div",{className:"min-w-0 flex-1",children:p}),x&&e.jsx("button",{type:"button",onClick:a=>U(a,F),onKeyDown:a=>a.stopPropagation(),disabled:G,className:"shrink-0 bg-ink px-3 py-2 font-display rounded-md text-sm font-normal text-ink-on transition-colors hover:bg-[#383838] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-[#d8d3c8]",children:x})]})]})}H.__docgenInfo={description:"Reusable entity card for recent apps, marketplace items, and owned apps.",methods:[],displayName:"CardDetailEntidad",props:{title:{required:!0,tsType:{name:"string"},description:""},description:{required:!1,tsType:{name:"string"},description:""},badges:{required:!1,tsType:{name:"ReadonlyArray",elements:[{name:"signature",type:"object",raw:`{\r
  readonly text: string;\r
  readonly color?: string;\r
  readonly className?: string;\r
}`,signature:{properties:[{key:"text",value:{name:"string",required:!0}},{key:"color",value:{name:"string",required:!1}},{key:"className",value:{name:"string",required:!1}}]}}],raw:`ReadonlyArray<{\r
  readonly text: string;\r
  readonly color?: string;\r
  readonly className?: string;\r
}>`},description:"",defaultValue:{value:"[]",computed:!1}},table:{required:!1,tsType:{name:"ReadonlyArray",elements:[{name:"signature",type:"object",raw:`{\r
  readonly label: string;\r
  readonly value: ReactNode;\r
}`,signature:{properties:[{key:"label",value:{name:"string",required:!0}},{key:"value",value:{name:"ReactNode",required:!0}}]}}],raw:`ReadonlyArray<{\r
  readonly label: string;\r
  readonly value: ReactNode;\r
}>`},description:""},metadata:{required:!1,tsType:{name:"ReactNode"},description:""},topRight:{required:!1,tsType:{name:"ReactNode"},description:""},imageSrc:{required:!1,tsType:{name:"string"},description:""},imageAlt:{required:!1,tsType:{name:"string"},description:"",defaultValue:{value:"''",computed:!1}},badgeText:{required:!1,tsType:{name:"string"},description:""},onClick:{required:!1,tsType:{name:"signature",type:"function",raw:"() => void",signature:{arguments:[],return:{name:"void"}}},description:""},actionLabel:{required:!1,tsType:{name:"string"},description:""},onActionClick:{required:!1,tsType:{name:"signature",type:"function",raw:"() => void",signature:{arguments:[],return:{name:"void"}}},description:""},actionDisabled:{required:!1,tsType:{name:"boolean"},description:"",defaultValue:{value:"false",computed:!1}},className:{required:!1,tsType:{name:"string"},description:"",defaultValue:{value:"''",computed:!1}}}};const Z={title:"UI/CardDetailEntidad",component:H,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{onClick:{action:"card clicked"},onActionClick:{action:"action clicked"}}},J=e.jsx("span",{className:"rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-fg-secondary",children:"Owner"}),i={args:{badgeText:"SD",title:"Soporte Documental",description:"Consulta y gestiona la documentación de tu organización.",metadata:"3 agentes · 8 miembros",onClick:r()}},o={args:{badgeText:"LI",title:"LKS Next INFO",description:"Agente especializado en información corporativa.",metadata:"Productividad · 4.8 ★",actionLabel:"Iniciar chat",onClick:r(),onActionClick:r()}},d={args:{badgeText:"RH",topRight:J,title:"RR.HH. Interno",description:"Agentes y fuentes de datos para la gestión interna.",metadata:"6 agentes · 12 miembros",onClick:r()}},l={args:{imageSrc:"https://placehold.co/68x68/202020/ffffff?text=AI",imageAlt:"AI",title:"Card con imagen",description:"La zona superior izquierda puede mostrar una imagen.",metadata:"Imagen · Variante visual",onClick:r()}},c={args:{badgeText:"TX",title:"Card con texto",description:"La zona superior izquierda también puede mostrar texto.",metadata:"Texto · Variante visual",onClick:r()}},u={args:{badgeText:"BG",title:"Card con etiquetas",description:"Las etiquetas se muestran debajo de la descripción.",badges:[{text:"Activo",color:"#22c55e"},{text:"Premium",color:"#3b82f6"},{text:"Nuevo",color:"#f97316"}],metadata:"3 etiquetas · Variante visual",onClick:r()}},m={args:{badgeText:"TB",title:"Card con tabla",description:"Las métricas se muestran en una tabla compacta.",table:[{label:"AGENTS",value:0},{label:"REPOS",value:0},{label:"DOMAINS",value:0},{label:"SILOS",value:0},{label:"COLLABS",value:1}],metadata:"Este contenido queda oculto",actionLabel:"Acción oculta",onClick:r(),onActionClick:r()}};var h,C,T;i.parameters={...i.parameters,docs:{...(h=i.parameters)==null?void 0:h.docs,source:{originalSource:`{
  args: {
    badgeText: 'SD',
    title: 'Soporte Documental',
    description: 'Consulta y gestiona la documentación de tu organización.',
    metadata: '3 agentes · 8 miembros',
    onClick: fn()
  }
}`,...(T=(C=i.parameters)==null?void 0:C.docs)==null?void 0:T.source}}};var N,A,q;o.parameters={...o.parameters,docs:{...(N=o.parameters)==null?void 0:N.docs,source:{originalSource:`{
  args: {
    badgeText: 'LI',
    title: 'LKS Next INFO',
    description: 'Agente especializado en información corporativa.',
    metadata: 'Productividad · 4.8 ★',
    actionLabel: 'Iniciar chat',
    onClick: fn(),
    onActionClick: fn()
  }
}`,...(q=(A=o.parameters)==null?void 0:A.docs)==null?void 0:q.source}}};var j,S,w;d.parameters={...d.parameters,docs:{...(j=d.parameters)==null?void 0:j.docs,source:{originalSource:`{
  args: {
    badgeText: 'RH',
    topRight: ownerBadge,
    title: 'RR.HH. Interno',
    description: 'Agentes y fuentes de datos para la gestión interna.',
    metadata: '6 agentes · 12 miembros',
    onClick: fn()
  }
}`,...(w=(S=d.parameters)==null?void 0:S.docs)==null?void 0:w.source}}};var I,R,L;l.parameters={...l.parameters,docs:{...(I=l.parameters)==null?void 0:I.docs,source:{originalSource:`{
  args: {
    imageSrc: 'https://placehold.co/68x68/202020/ffffff?text=AI',
    imageAlt: 'AI',
    title: 'Card con imagen',
    description: 'La zona superior izquierda puede mostrar una imagen.',
    metadata: 'Imagen · Variante visual',
    onClick: fn()
  }
}`,...(L=(R=l.parameters)==null?void 0:R.docs)==null?void 0:L.source}}};var D,B,z;c.parameters={...c.parameters,docs:{...(D=c.parameters)==null?void 0:D.docs,source:{originalSource:`{
  args: {
    badgeText: 'TX',
    title: 'Card con texto',
    description: 'La zona superior izquierda también puede mostrar texto.',
    metadata: 'Texto · Variante visual',
    onClick: fn()
  }
}`,...(z=(B=c.parameters)==null?void 0:B.docs)==null?void 0:z.source}}};var E,O,V;u.parameters={...u.parameters,docs:{...(E=u.parameters)==null?void 0:E.docs,source:{originalSource:`{
  args: {
    badgeText: 'BG',
    title: 'Card con etiquetas',
    description: 'Las etiquetas se muestran debajo de la descripción.',
    badges: [{
      text: 'Activo',
      color: '#22c55e'
    }, {
      text: 'Premium',
      color: '#3b82f6'
    }, {
      text: 'Nuevo',
      color: '#f97316'
    }],
    metadata: '3 etiquetas · Variante visual',
    onClick: fn()
  }
}`,...(V=(O=u.parameters)==null?void 0:O.docs)==null?void 0:V.source}}};var P,W,$;m.parameters={...m.parameters,docs:{...(P=m.parameters)==null?void 0:P.docs,source:{originalSource:`{
  args: {
    badgeText: 'TB',
    title: 'Card con tabla',
    description: 'Las métricas se muestran en una tabla compacta.',
    table: [{
      label: 'AGENTS',
      value: 0
    }, {
      label: 'REPOS',
      value: 0
    }, {
      label: 'DOMAINS',
      value: 0
    }, {
      label: 'SILOS',
      value: 0
    }, {
      label: 'COLLABS',
      value: 1
    }],
    metadata: 'Este contenido queda oculto',
    actionLabel: 'Acción oculta',
    onClick: fn(),
    onActionClick: fn()
  }
}`,...($=(W=m.parameters)==null?void 0:W.docs)==null?void 0:$.source}}};const ee=["RecentAppCard","MarketCard","MyAppCard","WithImage","WithTextBadge","WithBadges","WithTable"];export{o as MarketCard,d as MyAppCard,i as RecentAppCard,u as WithBadges,l as WithImage,m as WithTable,c as WithTextBadge,ee as __namedExportsOrder,Z as default};
