import{j as s}from"./jsx-runtime-9bc08dc0.js";import{c as t,S as C}from"./store-1448cd49.js";import"./index-f169cc97.js";/**
 * @license lucide-react v0.511.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const b=[["path",{d:"M12 8V4H8",key:"hb8ula"}],["rect",{width:"16",height:"12",x:"4",y:"8",rx:"2",key:"enze0r"}],["path",{d:"M2 14h2",key:"vft8re"}],["path",{d:"M20 14h2",key:"4cs60a"}],["path",{d:"M15 13v2",key:"1xurst"}],["path",{d:"M9 13v2",key:"rq6x2g"}]],M=t("bot",b);/**
 * @license lucide-react v0.511.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=[["path",{d:"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",key:"1rqfz7"}],["path",{d:"M14 2v4a2 2 0 0 0 2 2h4",key:"tnqrlb"}],["path",{d:"M10 9H8",key:"b1mrlr"}],["path",{d:"M16 13H8",key:"t4e002"}],["path",{d:"M16 17H8",key:"z1uh3a"}]],q=t("file-text",S);/**
 * @license lucide-react v0.511.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["path",{d:"M14 9a2 2 0 0 1-2 2H6l-4 4V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2z",key:"p1xzt8"}],["path",{d:"M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1",key:"1cx29u"}]],z=t("messages-square",T),_={Bot:M,FileText:q,MessagesSquare:z,Store:C};function f({icon:h,size:r=34,backgroundColor:k="#ebe6dd",iconColor:y="#816729",className:v=""}){const x=_[h];return s.jsx("span",{"aria-hidden":"true",className:`flex shrink-0 items-center justify-center overflow-hidden rounded-lg ${v}`,style:{width:r,height:r,backgroundColor:k},children:s.jsx(x,{size:r/2,color:y,strokeWidth:1.5})})}f.__docgenInfo={description:"Small colored icon tile used beside recent conversation rows.",methods:[],displayName:"BackgroundImage",props:{icon:{required:!0,tsType:{name:"union",raw:"'Bot' | 'FileText' | 'MessagesSquare' | 'Store'",elements:[{name:"literal",value:"'Bot'"},{name:"literal",value:"'FileText'"},{name:"literal",value:"'MessagesSquare'"},{name:"literal",value:"'Store'"}]},description:""},size:{required:!1,tsType:{name:"number"},description:"",defaultValue:{value:"34",computed:!1}},backgroundColor:{required:!1,tsType:{name:"string"},description:"",defaultValue:{value:"'#ebe6dd'",computed:!1}},iconColor:{required:!1,tsType:{name:"string"},description:"",defaultValue:{value:"'#816729'",computed:!1}},className:{required:!1,tsType:{name:"string"},description:"",defaultValue:{value:"''",computed:!1}}}};const F={title:"UI/BackgroundImage",component:f,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{icon:{control:"select",options:["Bot","FileText","MessagesSquare","Store"]}}},e={args:{icon:"Bot",size:34,backgroundColor:"#ebe6dd",iconColor:"#816729"}},o={args:{icon:"FileText",size:40,backgroundColor:"#eef4fb",iconColor:"#3a5573"}},a={args:{icon:"MessagesSquare",size:48,backgroundColor:"#eaf5ef",iconColor:"#1f7a4d"}};var n,c,i;e.parameters={...e.parameters,docs:{...(n=e.parameters)==null?void 0:n.docs,source:{originalSource:`{
  args: {
    icon: 'Bot',
    size: 34,
    backgroundColor: '#ebe6dd',
    iconColor: '#816729'
  }
}`,...(i=(c=e.parameters)==null?void 0:c.docs)==null?void 0:i.source}}};var d,l,u;o.parameters={...o.parameters,docs:{...(d=o.parameters)==null?void 0:d.docs,source:{originalSource:`{
  args: {
    icon: 'FileText',
    size: 40,
    backgroundColor: '#eef4fb',
    iconColor: '#3a5573'
  }
}`,...(u=(l=o.parameters)==null?void 0:l.docs)==null?void 0:u.source}}};var p,m,g;a.parameters={...a.parameters,docs:{...(p=a.parameters)==null?void 0:p.docs,source:{originalSource:`{
  args: {
    icon: 'MessagesSquare',
    size: 48,
    backgroundColor: '#eaf5ef',
    iconColor: '#1f7a4d'
  }
}`,...(g=(m=a.parameters)==null?void 0:m.docs)==null?void 0:g.source}}};const H=["RecentConversation","DocumentConversation","SupportConversation"];export{o as DocumentConversation,e as RecentConversation,a as SupportConversation,H as __namedExportsOrder,F as default};
