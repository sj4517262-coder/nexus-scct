import { useState, useEffect, useRef } from "react";
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";

// ═══════════════════════════════════════════════════════════
// DESIGN SYSTEM — Deep Navy / Electric Command Center
// ═══════════════════════════════════════════════════════════
const C = {
  bg0:"#020c1b",bg1:"#071428",bg2:"#0d1f3a",bg3:"#152b50",bg4:"#1e3a6a",
  bd1:"#1d3963",bd2:"#2d5580",
  sky:"#38bdf8",cyan:"#22d3ee",green:"#34d399",amber:"#fbbf24",
  red:"#f87171",purple:"#c084fc",orange:"#fb923c",pink:"#f472b6",
  t1:"#e2f0ff",t2:"#7db9e8",t3:"#4d7096",t4:"#2a4560",
  ff:'"DM Sans",-apple-system,sans-serif',
  ffM:'"IBM Plex Mono","Courier New",monospace',
  ffD:'"Rajdhani","DM Sans",sans-serif',
};
const rnd=(a,b)=>Math.random()*(b-a)+a;
const rndI=(a,b)=>Math.floor(rnd(a,b));
const sev2c=s=>({CRITICAL:C.red,HIGH:C.amber,MEDIUM:C.sky,LOW:C.green})[s]||C.t2;
const rsk2c=r=>({CRITICAL:C.red,HIGH:C.amber,MEDIUM:C.sky,LOW:C.green})[r]||C.t2;
const sts2c=s=>({ACTIVE:C.green,PROCESSING:C.sky,IDLE:C.t3,ALERT:C.red,CRITICAL:C.red,WARNING:C.amber,OPTIMAL:C.green})[s]||C.t2;
const geo2s=(lat,lng,w=800,h=380)=>({x:Math.round(((lng+180)/360)*w),y:Math.round(((90-lat)/180)*h)});

// ═══════════════════════════════════════════════════════════
// STATIC DATA
// ═══════════════════════════════════════════════════════════
const SUPPLIERS=[
  {id:"S001",name:"Shenzhen Electronics Co.",country:"China",rsk:"CRITICAL",score:32,vol:45000,cat:"Electronics",lat:22.5,lng:114.1},
  {id:"S002",name:"Vietnam Textile Group",country:"Vietnam",rsk:"MEDIUM",score:63,vol:28000,cat:"Textiles",lat:21.0,lng:105.8},
  {id:"S003",name:"Munich Industrial GmbH",country:"Germany",rsk:"LOW",score:91,vol:18000,cat:"Machinery",lat:48.1,lng:11.6},
  {id:"S004",name:"Bangalore Tech Parts",country:"India",rsk:"MEDIUM",score:67,vol:32000,cat:"Components",lat:12.9,lng:77.6},
  {id:"S005",name:"São Paulo Logistics SA",country:"Brazil",rsk:"HIGH",score:44,vol:15000,cat:"Raw Materials",lat:-23.5,lng:-46.6},
  {id:"S006",name:"Seoul Semiconductor",country:"S. Korea",rsk:"LOW",score:93,vol:38000,cat:"Semiconductors",lat:37.5,lng:127.0},
  {id:"S007",name:"Rotterdam Chemicals BV",country:"Netherlands",rsk:"LOW",score:87,vol:22000,cat:"Chemicals",lat:51.9,lng:4.5},
  {id:"S008",name:"Tokyo Precision Ltd",country:"Japan",rsk:"LOW",score:94,vol:41000,cat:"Precision Parts",lat:35.7,lng:139.7},
  {id:"S009",name:"Istanbul Metals Corp",country:"Turkey",rsk:"MEDIUM",score:56,vol:19000,cat:"Metals",lat:41.0,lng:28.9},
  {id:"S010",name:"Mexico City Auto Parts",country:"Mexico",rsk:"MEDIUM",score:74,vol:27000,cat:"Auto Parts",lat:19.4,lng:-99.1},
];
const WAREHOUSES=[
  {id:"W001",name:"Chicago Hub",city:"Chicago",cap:50000,util:78,sts:"OPTIMAL",lat:41.8,lng:-87.6},
  {id:"W002",name:"Dallas DC",city:"Dallas",cap:45000,util:91,sts:"CRITICAL",lat:32.8,lng:-96.8},
  {id:"W003",name:"Atlanta SE",city:"Atlanta",cap:35000,util:64,sts:"OPTIMAL",lat:33.7,lng:-84.4},
  {id:"W004",name:"Seattle Pacific",city:"Seattle",cap:40000,util:55,sts:"OPTIMAL",lat:47.6,lng:-122.3},
  {id:"W005",name:"Frankfurt Euro",city:"Frankfurt",cap:55000,util:82,sts:"WARNING",lat:50.1,lng:8.7},
  {id:"W006",name:"Amsterdam Port",city:"Amsterdam",cap:38000,util:71,sts:"OPTIMAL",lat:52.4,lng:4.9},
  {id:"W007",name:"Singapore APAC",city:"Singapore",cap:60000,util:88,sts:"WARNING",lat:1.3,lng:103.8},
  {id:"W008",name:"Dubai Gateway",city:"Dubai",cap:42000,util:67,sts:"OPTIMAL",lat:25.2,lng:55.3},
];
const AGENTS=[
  {id:"AG1",name:"Planner Agent",sts:"ACTIVE",task:"Orchestrating Q4 demand surge mitigation plan",decisions:47,conf:94,col:C.cyan},
  {id:"AG2",name:"Inventory Agent",sts:"PROCESSING",task:"Rebalancing Chicago→Dallas stock (8,400 units)",decisions:31,conf:87,col:C.green},
  {id:"AG3",name:"Logistics Agent",sts:"ACTIVE",task:"Rerouting SH→LA shipments via Singapore hub",decisions:28,conf:91,col:C.sky},
  {id:"AG4",name:"Supplier Risk Agent",sts:"ALERT",task:"Escalating Shenzhen Electronics factory shutdown",decisions:19,conf:96,col:C.red},
  {id:"AG5",name:"Demand Forecasting",sts:"ACTIVE",task:"TFT model: Black Friday spike +340% (±22%)",decisions:52,conf:88,col:C.purple},
  {id:"AG6",name:"Escalation Agent",sts:"IDLE",task:"Human approval queue — 2 decisions pending",decisions:8,conf:99,col:C.amber},
  {id:"AG7",name:"KPI Monitor Agent",sts:"ACTIVE",task:"OTIF at 87.3% — below 90% threshold alert sent",decisions:63,conf:100,col:C.orange},
  {id:"AG8",name:"Executive Summary",sts:"IDLE",task:"Generating EOD operational intelligence brief",decisions:12,conf:97,col:C.pink},
];
const DISRUPTIONS=[
  {id:"D001",type:"GEOPOLITICAL",sev:"CRITICAL",title:"Taiwan Strait Shipping Restriction",impact:"12 APAC routes affected",age:"2h 14m"},
  {id:"D002",type:"WEATHER",sev:"HIGH",title:"Typhoon Haikui — East China Sea",impact:"8 vessels rerouted, +4-6d delay",age:"3h 47m"},
  {id:"D003",type:"SUPPLIER",sev:"HIGH",title:"Shenzhen Electronics Factory Shutdown",impact:"Q4 electronics supply at risk",age:"5h 22m"},
  {id:"D004",type:"PORT",sev:"MEDIUM",title:"Rotterdam Port Workers Strike",impact:"23 containers held, 36h delay",age:"8h 01m"},
  {id:"D005",type:"DEMAND",sev:"MEDIUM",title:"Black Friday Demand Surge +340%",impact:"Dallas DC at 91% capacity",age:"12h 30m"},
];
const DECISIONS=[
  {id:"DC1",agent:"Planner Agent",action:"Emergency PO issued: Seoul Semiconductor $2.4M",conf:94,status:"AUTO-APPROVED",time:"14:28"},
  {id:"DC2",agent:"Logistics Agent",action:"Reroute SH→LA via Singapore (saves $45K)",conf:91,status:"AUTO-APPROVED",time:"13:58"},
  {id:"DC3",agent:"Inventory Agent",action:"Transfer Chicago→Dallas: 8,400 units",conf:87,status:"PENDING",time:"14:15"},
  {id:"DC4",agent:"Escalation Agent",action:"$8.7M alternative supplier contract approval",conf:72,status:"HUMAN REQUIRED",time:"13:45"},
  {id:"DC5",agent:"Planner Agent",action:"Safety stock increase: Electronics category +40%",conf:89,status:"AUTO-APPROVED",time:"13:05"},
];
const EVENTS_INIT=[
  {t:"14:33",type:"DISRUPTION",sev:"CRITICAL",msg:"Typhoon trajectory updated — 8 vessels rerouted via Lombok Strait",agent:"Logistics Agent"},
  {t:"14:28",type:"DECISION",sev:"HIGH",msg:"Emergency PO issued: Seoul Semiconductor $2.4M (auto-approved)",agent:"Planner Agent"},
  {t:"14:21",type:"ALERT",sev:"HIGH",msg:"Dallas warehouse utilization crossed 90% critical threshold",agent:"KPI Monitor"},
  {t:"14:15",type:"OPTIMIZATION",sev:"MEDIUM",msg:"Inventory rebalance queued: Chicago→Dallas 8,400 units initiated",agent:"Inventory Agent"},
  {t:"14:09",type:"FORECAST",sev:"MEDIUM",msg:"Black Friday demand forecast revised upward: +340% (conf: ±22%)",agent:"Demand Forecasting"},
  {t:"14:03",type:"RISK",sev:"HIGH",msg:"Supplier S001 risk score deteriorated: 61→32 (factory closure)",agent:"Supplier Risk Agent"},
  {t:"13:58",type:"DECISION",sev:"MEDIUM",msg:"Route SH→LA via Singapore approved — cost savings $45K",agent:"Logistics Agent"},
  {t:"13:45",type:"ESCALATION",sev:"CRITICAL",msg:"HUMAN APPROVAL REQUIRED: $8.7M alternative supplier contract",agent:"Escalation Agent"},
  {t:"13:39",type:"UPDATE",sev:"LOW",msg:"Frankfurt Euro hub rebalancing complete — utilization 82%→71%",agent:"Inventory Agent"},
  {t:"13:22",type:"UPDATE",sev:"LOW",msg:"OTIF recovered to 87.3% post emergency rerouting operations",agent:"KPI Monitor"},
  {t:"13:05",type:"DECISION",sev:"HIGH",msg:"Safety stock increase approved: Electronics category +40%",agent:"Planner Agent"},
  {t:"12:48",type:"ALERT",sev:"MEDIUM",msg:"Singapore APAC hub approaching capacity threshold (88%)",agent:"KPI Monitor"},
];
const NEW_EVENTS_POOL=[
  {type:"DECISION",sev:"MEDIUM",msg:"Demand model retrained after statistical drift detection",agent:"Demand Forecasting"},
  {type:"ALERT",sev:"HIGH",msg:"Vietnam port congestion detected — 3 shipments delayed",agent:"Logistics Agent"},
  {type:"OPTIMIZATION",sev:"LOW",msg:"EOQ recalculated for 47 SKUs — reorder quantities updated",agent:"Inventory Agent"},
  {type:"RISK",sev:"MEDIUM",msg:"Istanbul Metals Corp payment delay — risk score +12 points",agent:"Supplier Risk Agent"},
  {type:"FORECAST",sev:"LOW",msg:"Week 48 forecast confidence interval narrowed to ±14%",agent:"Demand Forecasting"},
  {type:"ESCALATION",sev:"HIGH",msg:"Emergency cross-dock transfer requires executive approval",agent:"Escalation Agent"},
];

// Data Generators
const genForecast=()=>Array.from({length:28},(_,i)=>({
  d:`D${i-14}`,
  actual:i<15?Math.round(rnd(8500,11500)):null,
  forecast:Math.round(rnd(9000,13500)),
  hi:Math.round(rnd(12000,15500)),
  lo:Math.round(rnd(6500,9000)),
}));
const genKPI24h=()=>Array.from({length:24},(_,i)=>({
  h:`${String(i).padStart(2,"0")}h`,
  otif:+rnd(80,93).toFixed(1),
  fill:+rnd(89,97).toFixed(1),
  util:+rnd(72,91).toFixed(1),
}));
const genKPIs=()=>({
  otif:+rnd(85,89.5).toFixed(1),fill:+rnd(93,96).toFixed(1),
  invTurn:+rnd(7.1,7.8).toFixed(1),whUtil:+rnd(76,82).toFixed(0),
  trCost:+rnd(2.3,2.8).toFixed(2),stRisk:+rnd(3.2,5.1).toFixed(1),
  supRel:+rnd(87,92).toFixed(1),delRisk:+rnd(16,22).toFixed(1),
});
const genInvHist=()=>Array.from({length:14},(_,i)=>({
  d:`W${Math.floor(i/2)+45}D${(i%2)+1}`,
  actual:Math.round(rnd(35000,55000)),target:45000,safety:15000,
}));

// ═══════════════════════════════════════════════════════════
// MICRO COMPONENTS
// ═══════════════════════════════════════════════════════════
const Dot=({color=C.green,size=8})=>(
  <span style={{display:"inline-block",width:size,height:size,borderRadius:"50%",
    background:color,flexShrink:0,boxShadow:`0 0 ${size*1.5}px ${color}55`,
    animation:"pulse 2s ease-in-out infinite"}}/>
);
const Chip=({label,color=C.sky})=>(
  <span style={{padding:"2px 7px",borderRadius:3,fontSize:9,fontWeight:700,
    letterSpacing:"0.1em",color,border:`1px solid ${color}55`,
    background:`${color}18`,textTransform:"uppercase",whiteSpace:"nowrap",
    fontFamily:C.ffM,display:"inline-block"}}>{label}</span>
);
const Tip=({active,payload,label})=>{
  if(!active||!payload?.length)return null;
  return(<div style={{background:C.bg3,border:`1px solid ${C.bd2}`,borderRadius:8,padding:"8px 12px",fontFamily:C.ffM,fontSize:11}}>
    <div style={{color:C.t3,marginBottom:4}}>{label}</div>
    {payload.map((p,i)=>(
      <div key={i} style={{color:p.color||C.t1}}>{p.name}: <strong>{typeof p.value==="number"?p.value.toFixed(1):p.value}</strong></div>
    ))}
  </div>);
};

// ═══════════════════════════════════════════════════════════
// SUPPLY CHAIN MAP SVG
// ═══════════════════════════════════════════════════════════
const SCMap=()=>{
  const [hov,setHov]=useState(null);
  const sNodes=SUPPLIERS.map(s=>({...geo2s(s.lat,s.lng),...s,nt:"supplier"}));
  const wNodes=WAREHOUSES.map(w=>({...geo2s(w.lat,w.lng),...w,nt:"warehouse"}));
  const ports=[
    {...geo2s(31.2,121.5),label:"Shanghai",id:"P1",nt:"port"},
    {...geo2s(1.3,103.8),label:"Singapore",id:"P2",nt:"port"},
    {...geo2s(51.9,4.5),label:"Rotterdam",id:"P3",nt:"port"},
    {...geo2s(33.7,-118.3),label:"LA Port",id:"P4",nt:"port"},
    {...geo2s(29.7,-95.0),label:"Houston",id:"P5",nt:"port"},
    {...geo2s(25.2,55.3),label:"Dubai",id:"P6",nt:"port"},
  ];
  const routes=[
    {f:sNodes[0],t:ports[0],active:true},{f:ports[0],t:ports[1],active:true},
    {f:ports[1],t:ports[3],active:true},{f:sNodes[5],t:ports[0],active:false},
    {f:sNodes[7],t:ports[0],active:false},{f:sNodes[2],t:ports[2],active:false},
    {f:ports[2],t:wNodes[4],active:false},{f:ports[2],t:wNodes[5],active:false},
    {f:ports[3],t:wNodes[0],active:false},{f:ports[3],t:wNodes[1],active:true},
    {f:sNodes[3],t:ports[5],active:false},{f:ports[5],t:wNodes[7],active:false},
    {f:sNodes[9],t:ports[4],active:false},{f:ports[4],t:wNodes[1],active:false},
  ];
  return(
    <svg viewBox="0 0 800 380" style={{width:"100%",borderRadius:6,background:"#010a18"}}>
      {Array.from({length:8},(_,i)=><line key={`h${i}`} x1="0" y1={i*54} x2="800" y2={i*54} stroke={C.bd1} strokeWidth="0.4" opacity="0.4"/>)}
      {Array.from({length:17},(_,i)=><line key={`v${i}`} x1={i*50} y1="0" x2={i*50} y2="380" stroke={C.bd1} strokeWidth="0.4" opacity="0.4"/>)}
      {routes.map((r,i)=>r.f&&r.t&&(
        <line key={i} x1={r.f.x} y1={r.f.y} x2={r.t.x} y2={r.t.y}
          stroke={r.active?C.sky:C.bd2} strokeWidth={r.active?1.5:0.8}
          strokeDasharray={r.active?"7 4":"none"} opacity={r.active?0.9:0.35}/>
      ))}
      {sNodes.map(n=>(
        <g key={n.id} onMouseEnter={()=>setHov(n)} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}>
          <circle cx={n.x} cy={n.y} r={10} fill={rsk2c(n.rsk)} opacity={0.15}/>
          <circle cx={n.x} cy={n.y} r={4.5} fill={rsk2c(n.rsk)} opacity={0.9}/>
          {hov?.id===n.id&&(
            <foreignObject x={Math.min(n.x+12,620)} y={n.y-24} width={168} height={52}>
              <div style={{background:C.bg3,border:`1px solid ${C.bd2}`,borderRadius:6,padding:"6px 10px",fontFamily:C.ff}}>
                <div style={{fontSize:11,fontWeight:700,color:C.t1}}>{n.name}</div>
                <div style={{fontSize:9,color:rsk2c(n.rsk),fontFamily:C.ffM}}>{n.rsk} RISK · Score: {n.score}/100</div>
              </div>
            </foreignObject>
          )}
        </g>
      ))}
      {wNodes.map(n=>(
        <g key={n.id} onMouseEnter={()=>setHov(n)} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}>
          <rect x={n.x-8} y={n.y-8} width={16} height={16} fill={sts2c(n.sts)} opacity={0.15}/>
          <rect x={n.x-4} y={n.y-4} width={8} height={8} fill={sts2c(n.sts)} opacity={0.9}/>
          {hov?.id===n.id&&(
            <foreignObject x={Math.min(n.x+12,620)} y={n.y-24} width={160} height={52}>
              <div style={{background:C.bg3,border:`1px solid ${C.bd2}`,borderRadius:6,padding:"6px 10px",fontFamily:C.ff}}>
                <div style={{fontSize:11,fontWeight:700,color:C.t1}}>{n.name}</div>
                <div style={{fontSize:9,color:sts2c(n.sts),fontFamily:C.ffM}}>{n.sts} · {n.util}% utilized</div>
              </div>
            </foreignObject>
          )}
        </g>
      ))}
      {ports.map(p=>(
        <g key={p.id}>
          <polygon points={`${p.x},${p.y-7} ${p.x-5},${p.y+4} ${p.x+5},${p.y+4}`} fill={C.cyan} opacity={0.9}/>
          <text x={p.x+8} y={p.y+4} fill={C.t3} fontSize={8} fontFamily={C.ffM}>{p.label}</text>
        </g>
      ))}
      <g transform="translate(8,352)">
        <circle cx={5} cy={4} r={4} fill={C.red}/><text x={13} y={7} fill={C.t3} fontSize={8} fontFamily={C.ffM}>Critical</text>
        <circle cx={74} cy={4} r={4} fill={C.amber}/><text x={82} y={7} fill={C.t3} fontSize={8} fontFamily={C.ffM}>High Risk</text>
        <circle cx={148} cy={4} r={4} fill={C.green}/><text x={156} y={7} fill={C.t3} fontSize={8} fontFamily={C.ffM}>Low Risk</text>
        <rect x={216} y={0} width={8} height={8} fill={C.sky}/><text x={228} y={7} fill={C.t3} fontSize={8} fontFamily={C.ffM}>Warehouse</text>
        <polygon points="293,0 289,8 297,8" fill={C.cyan}/><text x={302} y={7} fill={C.t3} fontSize={8} fontFamily={C.ffM}>Port</text>
        <line x1={350} y1={4} x2={370} y2={4} stroke={C.sky} strokeWidth={1.5} strokeDasharray="5 3"/>
        <text x={374} y={7} fill={C.t3} fontSize={8} fontFamily={C.ffM}>Active Route</text>
      </g>
    </svg>
  );
};

// ═══════════════════════════════════════════════════════════
// DASHBOARD VIEW
// ═══════════════════════════════════════════════════════════
const DashboardView=({kpis,events,forecast,kpi24h})=>{
  const kpiCards=[
    {label:"OTIF Score",val:kpis.otif+"%",delta:-2.1,col:kpis.otif>90?C.green:C.amber},
    {label:"Fill Rate",val:kpis.fill+"%",delta:+0.3,col:C.green},
    {label:"Inv. Turnover",val:kpis.invTurn+"x",delta:+0.2,col:C.sky},
    {label:"WH Utilization",val:kpis.whUtil+"%",delta:+4.2,col:+kpis.whUtil>85?C.red:C.amber},
    {label:"Transport Cost",val:"$"+kpis.trCost+"M",delta:+0.3,col:C.amber},
    {label:"Stockout Risk",val:kpis.stRisk+"%",delta:-1.4,col:C.green},
    {label:"Supplier Rel.",val:kpis.supRel+"%",delta:-3.2,col:kpis.supRel>90?C.green:C.amber},
    {label:"Delay Risk",val:kpis.delRisk+"%",delta:+2.1,col:C.red},
  ];
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{display:"grid",gridTemplateColumns:"repeat(8,1fr)",gap:8}}>
        {kpiCards.map(k=>(
          <div key={k.label} style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:10,
            padding:"12px 12px",borderLeft:`3px solid ${k.col}`}}>
            <div style={{fontSize:8,color:C.t3,letterSpacing:"0.1em",textTransform:"uppercase",
              marginBottom:5,fontFamily:C.ffM}}>{k.label}</div>
            <div style={{fontSize:20,fontWeight:700,color:k.col,fontFamily:C.ffD,lineHeight:1}}>{k.val}</div>
            <div style={{fontSize:9,color:k.delta>0?C.red:C.green,marginTop:4,fontFamily:C.ffM}}>
              {k.delta>0?"▲":"▼"} {Math.abs(k.delta)}% vs 24h
            </div>
          </div>
        ))}
      </div>
      <div style={{background:`${C.red}10`,border:`1px solid ${C.red}30`,borderRadius:8,
        padding:"8px 14px",display:"flex",alignItems:"center",gap:10,overflow:"hidden"}}>
        <Dot color={C.red} size={9}/>
        <span style={{color:C.red,fontWeight:700,fontSize:10,fontFamily:C.ffM,whiteSpace:"nowrap"}}>3 ACTIVE DISRUPTIONS —</span>
        {DISRUPTIONS.slice(0,3).map((d,i)=>(
          <span key={d.id} style={{display:"flex",alignItems:"center",gap:6}}>
            {i>0&&<span style={{color:C.t4}}>|</span>}
            <Chip label={d.type} color={sev2c(d.sev)}/>
            <span style={{fontSize:11,color:i===0?C.t1:C.t2}}>{d.title}</span>
          </span>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 295px",gap:12}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
            <span style={{fontFamily:C.ffD,fontSize:13,fontWeight:700,letterSpacing:"0.08em",
              color:C.t1,textTransform:"uppercase"}}>Global Supply Chain Network</span>
            <div style={{display:"flex",alignItems:"center",gap:6}}>
              <Dot color={C.green} size={6}/><span style={{fontSize:10,color:C.t2,fontFamily:C.ffM}}>LIVE</span>
            </div>
          </div>
          <SCMap/>
        </div>
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:12,flex:1,overflow:"hidden"}}>
            <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.1em",
              color:C.t1,textTransform:"uppercase",marginBottom:8}}>AI Agent Status</div>
            {AGENTS.map(a=>(
              <div key={a.id} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${C.bg3}`}}>
                <Dot color={sts2c(a.sts)} size={6}/>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontSize:10,fontWeight:600,color:C.t1}}>{a.name}</div>
                  <div style={{fontSize:9,color:C.t3,overflow:"hidden",textOverflow:"ellipsis",
                    whiteSpace:"nowrap",fontFamily:C.ffM}}>{a.task}</div>
                </div>
                <Chip label={a.sts} color={sts2c(a.sts)}/>
              </div>
            ))}
          </div>
          <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:12}}>
            <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.1em",
              color:C.t1,textTransform:"uppercase",marginBottom:8}}>Latest Events</div>
            {events.slice(0,5).map((e,i)=>(
              <div key={i} style={{padding:"4px 0",borderBottom:`1px solid ${C.bg3}`,display:"flex",gap:6}}>
                <span style={{fontSize:8,color:C.t3,fontFamily:C.ffM,whiteSpace:"nowrap",marginTop:2}}>{e.t||"--:--"}</span>
                <div>
                  <span style={{fontSize:9,color:sev2c(e.sev),fontFamily:C.ffM}}>[{e.type}] </span>
                  <span style={{fontSize:9,color:C.t2}}>{e.msg.slice(0,55)}…</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",color:C.t1,textTransform:"uppercase",marginBottom:3}}>Demand Forecast Engine</div>
          <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,marginBottom:8}}>TFT Model · 28-Day Horizon · Confidence: 88%</div>
          <ResponsiveContainer width="100%" height={155}>
            <AreaChart data={forecast} margin={{top:5,right:5,left:-25,bottom:0}}>
              <defs>
                <linearGradient id="fg1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.sky} stopOpacity={0.35}/><stop offset="95%" stopColor={C.sky} stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.bg3}/>
              <XAxis dataKey="d" tick={{fill:C.t3,fontSize:8}} interval={6}/>
              <YAxis tick={{fill:C.t3,fontSize:8}}/>
              <Tooltip content={<Tip/>}/>
              <Area type="monotone" dataKey="hi" stroke="none" fill={C.sky} fillOpacity={0.05} name="Upper CI"/>
              <Area type="monotone" dataKey="forecast" stroke={C.sky} strokeWidth={2} fill="url(#fg1)" name="Forecast"/>
              <Line type="monotone" dataKey="actual" stroke={C.green} strokeWidth={2} dot={false} name="Actual"/>
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",color:C.t1,textTransform:"uppercase",marginBottom:3}}>24-Hour KPI Trend</div>
          <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,marginBottom:8}}>Real-time operational health indicators</div>
          <ResponsiveContainer width="100%" height={155}>
            <LineChart data={kpi24h} margin={{top:5,right:5,left:-25,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.bg3}/>
              <XAxis dataKey="h" tick={{fill:C.t3,fontSize:8}} interval={5}/>
              <YAxis tick={{fill:C.t3,fontSize:8}} domain={[70,100]}/>
              <Tooltip content={<Tip/>}/>
              <Line type="monotone" dataKey="otif" stroke={C.amber} strokeWidth={2} dot={false} name="OTIF %"/>
              <Line type="monotone" dataKey="fill" stroke={C.green} strokeWidth={2} dot={false} name="Fill Rate %"/>
              <Line type="monotone" dataKey="util" stroke={C.sky} strokeWidth={2} dot={false} name="WH Util %"/>
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// AGENTS VIEW
// ═══════════════════════════════════════════════════════════
const AgentsView=()=>{
  const [sel,setSel]=useState(null);
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
        {AGENTS.map(a=>(
          <div key={a.id} onClick={()=>setSel(sel?.id===a.id?null:a)} style={{
            background:sel?.id===a.id?C.bg3:C.bg1,
            border:`1px solid ${sel?.id===a.id?a.col+"70":C.bd1}`,
            borderRadius:10,padding:14,cursor:"pointer",
            borderLeft:`3px solid ${a.col}`,transition:"all 0.15s"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
              <div style={{display:"flex",alignItems:"center",gap:7}}>
                <Dot color={sts2c(a.sts)} size={7}/>
                <span style={{fontSize:11,fontWeight:700,color:C.t1,fontFamily:C.ffD}}>{a.name}</span>
              </div>
              <Chip label={a.sts} color={sts2c(a.sts)}/>
            </div>
            <div style={{fontSize:10,color:C.t2,marginBottom:8,lineHeight:1.4,fontFamily:C.ffM}}>{a.task}</div>
            <div style={{display:"flex",justifyContent:"space-between",fontSize:9,color:C.t3,fontFamily:C.ffM,marginBottom:6}}>
              <span>Decisions: <span style={{color:a.col,fontWeight:700}}>{a.decisions}</span></span>
              <span>Conf: <span style={{color:a.col,fontWeight:700}}>{a.conf}%</span></span>
            </div>
            <div style={{height:3,background:C.bg4,borderRadius:2}}>
              <div style={{height:"100%",width:`${a.conf}%`,background:a.col,borderRadius:2}}/>
            </div>
          </div>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:13,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Autonomous Decision Log</div>
          {DECISIONS.map(d=>(
            <div key={d.id} style={{padding:"10px 12px",borderRadius:8,marginBottom:8,
              background:C.bg2,border:`1px solid ${C.bd1}`}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:5}}>
                <Chip label={d.agent} color={C.sky}/>
                <Chip label={d.status} color={d.status==="AUTO-APPROVED"?C.green:d.status==="HUMAN REQUIRED"?C.red:C.amber}/>
              </div>
              <div style={{fontSize:11,color:C.t1,margin:"5px 0"}}>{d.action}</div>
              <div style={{display:"flex",justifyContent:"space-between",fontSize:9,color:C.t3,fontFamily:C.ffM}}>
                <span>Confidence: <span style={{color:C.sky}}>{d.conf}%</span></span>
                <span>{d.time}</span>
              </div>
            </div>
          ))}
        </div>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:13,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Agent Orchestration Flow</div>
          <svg viewBox="0 0 420 400" style={{width:"100%"}}>
            <rect x="145" y="12" width="130" height="42" rx="6" fill={`${C.cyan}20`} stroke={C.cyan} strokeWidth={1}/>
            <text x="210" y="30" textAnchor="middle" fill={C.cyan} fontSize={10} fontFamily={C.ffD} fontWeight="700">PLANNER AGENT</text>
            <text x="210" y="45" textAnchor="middle" fill={C.t3} fontSize={8} fontFamily={C.ffM}>Master Orchestrator</text>
            {[
              {x:15,y:90,label:"Inventory Agent",col:C.green,sub:"PROCESSING"},
              {x:155,y:90,label:"Logistics Agent",col:C.sky,sub:"ACTIVE"},
              {x:290,y:90,label:"Supplier Risk",col:C.red,sub:"ALERT"},
              {x:15,y:175,label:"Demand Forecast",col:C.purple,sub:"ACTIVE"},
              {x:155,y:175,label:"KPI Monitor",col:C.orange,sub:"ACTIVE"},
              {x:290,y:175,label:"Escalation",col:C.amber,sub:"IDLE"},
            ].map((n,i)=>(
              <g key={i}>
                <line x1="210" y1="54" x2={n.x+65} y2={n.y} stroke={C.bd2} strokeWidth={0.8} strokeDasharray="4 3"/>
                <rect x={n.x} y={n.y} width={130} height={38} rx={5} fill={`${n.col}15`} stroke={n.col} strokeWidth={0.8}/>
                <text x={n.x+65} y={n.y+16} textAnchor="middle" fill={n.col} fontSize={9} fontFamily={C.ffD} fontWeight="600">{n.label}</text>
                <text x={n.x+65} y={n.y+29} textAnchor="middle" fill={C.t3} fontSize={8} fontFamily={C.ffM}>{n.sub}</text>
              </g>
            ))}
            <line x1="355" y1="213" x2="280" y2="265" stroke={C.amber} strokeWidth={0.8} strokeDasharray="4 3"/>
            <line x1="155" y1="213" x2="205" y2="265" stroke={C.amber} strokeWidth={0.8} strokeDasharray="4 3"/>
            <rect x="125" y="265" width="170" height="42" rx="6" fill={`${C.amber}15`} stroke={C.amber} strokeWidth={1} strokeDasharray="5 3"/>
            <text x="210" y="285" textAnchor="middle" fill={C.amber} fontSize={10} fontFamily={C.ffD} fontWeight="700">HUMAN APPROVAL</text>
            <text x="210" y="300" textAnchor="middle" fill={C.t3} fontSize={8} fontFamily={C.ffM}>2 pending · $8.7M threshold</text>
            <line x1="210" y1="307" x2="210" y2="342" stroke={C.pink} strokeWidth={0.8} strokeDasharray="3 3"/>
            <rect x="115" y="342" width="190" height="36" rx="5" fill={`${C.pink}12`} stroke={C.pink} strokeWidth={0.8}/>
            <text x="210" y="360" textAnchor="middle" fill={C.pink} fontSize={9} fontFamily={C.ffD} fontWeight="600">EXECUTIVE SUMMARY AGENT</text>
            <text x="210" y="372" textAnchor="middle" fill={C.t3} fontSize={8} fontFamily={C.ffM}>C-Suite Reporting Pipeline</text>
          </svg>
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// INVENTORY VIEW
// ═══════════════════════════════════════════════════════════
const InventoryView=()=>{
  const hist=genInvHist();
  const barData=WAREHOUSES.map(w=>({
    name:w.city.length>6?w.city.slice(0,6):w.city,
    util:w.util,col:w.util>90?C.red:w.util>80?C.amber:C.green,
  }));
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:16}}>
        <div style={{fontFamily:C.ffD,fontSize:13,fontWeight:700,letterSpacing:"0.08em",
          color:C.t1,textTransform:"uppercase",marginBottom:14}}>Warehouse Capacity Intelligence</div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
          {WAREHOUSES.map(w=>(
            <div key={w.id} style={{background:C.bg2,borderRadius:8,padding:"12px 14px",
              border:`1px solid ${w.sts==="CRITICAL"?C.red+"40":C.bd1}`}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6}}>
                <div style={{fontSize:11,fontWeight:700,color:C.t1}}>{w.name}</div>
                <Chip label={w.sts} color={sts2c(w.sts)}/>
              </div>
              <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,marginBottom:8}}>{w.city} · Cap: {(w.cap/1000).toFixed(0)}K units</div>
              <div style={{height:8,background:C.bg4,borderRadius:4,overflow:"hidden",marginBottom:6}}>
                <div style={{height:"100%",width:`${w.util}%`,borderRadius:4,
                  background:w.util>90?C.red:w.util>80?C.amber:C.green}}/>
              </div>
              <div style={{display:"flex",justifyContent:"space-between",fontSize:10,fontFamily:C.ffM}}>
                <span style={{color:w.util>90?C.red:w.util>80?C.amber:C.green,fontWeight:700}}>{w.util}%</span>
                <span style={{color:C.t3}}>{(w.cap*w.util/100000).toFixed(0)}K / {(w.cap/1000).toFixed(0)}K</span>
              </div>
              <div style={{marginTop:8,display:"flex",gap:8}}>
                {[["Reorder","30%",C.sky],["Safety","15%",C.green]].map(([l,v,col])=>(
                  <div key={l} style={{flex:1,background:C.bg3,borderRadius:4,padding:"4px 6px"}}>
                    <div style={{fontSize:8,color:C.t3,fontFamily:C.ffM}}>{l}</div>
                    <div style={{fontSize:10,color:col,fontWeight:600}}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:12}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Inventory Level History — All Warehouses</div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={hist} margin={{top:5,right:5,left:-15,bottom:0}}>
              <defs>
                <linearGradient id="invg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.green} stopOpacity={0.4}/><stop offset="95%" stopColor={C.green} stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.bg3}/>
              <XAxis dataKey="d" tick={{fill:C.t3,fontSize:9}}/>
              <YAxis tick={{fill:C.t3,fontSize:9}}/>
              <Tooltip content={<Tip/>}/>
              <Area type="monotone" dataKey="actual" stroke={C.green} strokeWidth={2} fill="url(#invg)" name="Inventory"/>
              <Line type="monotone" dataKey="target" stroke={C.sky} strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="Target"/>
              <Line type="monotone" dataKey="safety" stroke={C.red} strokeWidth={1} strokeDasharray="3 3" dot={false} name="Safety Stock"/>
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Utilization by Location</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={barData} layout="vertical" margin={{top:0,right:5,left:20,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.bg3}/>
              <XAxis type="number" tick={{fill:C.t3,fontSize:9}} domain={[0,100]}/>
              <YAxis type="category" dataKey="name" tick={{fill:C.t3,fontSize:9}}/>
              <Tooltip content={<Tip/>}/>
              <Bar dataKey="util" name="Utilization %">
                {barData.map((e,i)=><Cell key={i} fill={e.col}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
        <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
          color:C.t1,textTransform:"uppercase",marginBottom:12}}>AI Optimization Recommendations</div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10}}>
          {[
            {title:"REORDER: Dallas DC",msg:"At 91% — restock 9,450 units immediately to avoid stockout in 72h",sev:"CRITICAL"},
            {title:"REBALANCE: Chicago→Dallas",msg:"Transfer 8,400 units from Chicago (78%) to reduce Dallas critical level",sev:"HIGH"},
            {title:"SAFETY STOCK: Electronics",msg:"Increase safety stock +40% for electronics due to Shenzhen supplier risk",sev:"MEDIUM"},
          ].map((a,i)=>(
            <div key={i} style={{background:C.bg2,borderRadius:8,padding:"12px 14px",borderLeft:`3px solid ${sev2c(a.sev)}`}}>
              <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}>
                <Dot color={sev2c(a.sev)} size={7}/>
                <span style={{fontSize:10,fontWeight:700,color:sev2c(a.sev),fontFamily:C.ffM}}>{a.title}</span>
              </div>
              <div style={{fontSize:11,color:C.t2,lineHeight:1.4,marginBottom:10}}>{a.msg}</div>
              <div style={{display:"flex",gap:8}}>
                {["APPROVE","DEFER"].map((btn,bi)=>(
                  <button key={btn} style={{padding:"5px 12px",borderRadius:5,fontSize:10,cursor:"pointer",fontFamily:C.ffM,fontWeight:700,
                    background:bi===0?`${sev2c(a.sev)}20`:"transparent",
                    border:`1px solid ${bi===0?sev2c(a.sev)+"60":C.bd2}`,
                    color:bi===0?sev2c(a.sev):C.t3}}>{btn}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// SUPPLIERS VIEW
// ═══════════════════════════════════════════════════════════
const SuppliersView=()=>{
  const riskBar=SUPPLIERS.map(s=>({name:s.country,score:s.score,fill:rsk2c(s.rsk)}));
  const pieData=[
    {name:"LOW",value:SUPPLIERS.filter(s=>s.rsk==="LOW").reduce((a,s)=>a+s.vol,0)/1000,col:C.green},
    {name:"MEDIUM",value:SUPPLIERS.filter(s=>s.rsk==="MEDIUM").reduce((a,s)=>a+s.vol,0)/1000,col:C.sky},
    {name:"HIGH",value:SUPPLIERS.filter(s=>s.rsk==="HIGH").reduce((a,s)=>a+s.vol,0)/1000,col:C.amber},
    {name:"CRITICAL",value:SUPPLIERS.filter(s=>s.rsk==="CRITICAL").reduce((a,s)=>a+s.vol,0)/1000,col:C.red},
  ];
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
        {[
          {label:"Critical Suppliers",count:1,col:C.red,note:"Immediate action required"},
          {label:"High Risk",count:1,col:C.amber,note:"Enhanced monitoring active"},
          {label:"Medium Risk",count:4,col:C.sky,note:"Under surveillance"},
          {label:"Low Risk (Reliable)",count:4,col:C.green,note:"Operating normally"},
        ].map(r=>(
          <div key={r.label} style={{background:C.bg1,border:`1px solid ${r.col}30`,borderRadius:10,padding:"14px 16px",borderLeft:`3px solid ${r.col}`}}>
            <div style={{fontSize:30,fontWeight:700,color:r.col,fontFamily:C.ffD}}>{r.count}</div>
            <div style={{fontSize:11,fontWeight:600,color:C.t1,marginTop:4}}>{r.label}</div>
            <div style={{fontSize:10,color:C.t3,marginTop:3,fontFamily:C.ffM}}>{r.note}</div>
          </div>
        ))}
      </div>
      <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
        <div style={{fontFamily:C.ffD,fontSize:13,fontWeight:700,letterSpacing:"0.08em",
          color:C.t1,textTransform:"uppercase",marginBottom:12}}>Supplier Risk Intelligence Matrix</div>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr style={{borderBottom:`1px solid ${C.bd1}`}}>
              {["Supplier","Country","Category","Risk Level","Score","Vol/mo","Status","Action"].map(h=>(
                <th key={h} style={{textAlign:"left",padding:"8px 10px",fontSize:9,color:C.t3,fontFamily:C.ffM,
                  letterSpacing:"0.1em",textTransform:"uppercase",fontWeight:600}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SUPPLIERS.map((s,i)=>(
              <tr key={s.id} style={{borderBottom:`1px solid ${C.bg3}`,background:i%2===0?C.bg2+"50":"transparent"}}>
                <td style={{padding:"8px 10px",fontSize:11,fontWeight:600,color:C.t1}}>{s.name}</td>
                <td style={{padding:"8px 10px",fontSize:11,color:C.t2}}>{s.country}</td>
                <td style={{padding:"8px 10px",fontSize:11,color:C.t2}}>{s.cat}</td>
                <td style={{padding:"8px 10px"}}><Chip label={s.rsk} color={rsk2c(s.rsk)}/></td>
                <td style={{padding:"8px 10px",fontFamily:C.ffM}}>
                  <div style={{display:"flex",alignItems:"center",gap:8}}>
                    <div style={{flex:1,height:6,background:C.bg4,borderRadius:3}}>
                      <div style={{height:"100%",width:`${s.score}%`,background:rsk2c(s.rsk),borderRadius:3}}/>
                    </div>
                    <span style={{fontSize:10,color:rsk2c(s.rsk),fontWeight:700,minWidth:24}}>{s.score}</span>
                  </div>
                </td>
                <td style={{padding:"8px 10px",fontSize:11,color:C.t2,fontFamily:C.ffM}}>{(s.vol/1000).toFixed(0)}K u</td>
                <td style={{padding:"8px 10px"}}>
                  <div style={{display:"flex",alignItems:"center",gap:5}}>
                    <Dot color={rsk2c(s.rsk)} size={6}/>
                    <span style={{fontSize:9,color:C.t2,fontFamily:C.ffM}}>
                      {s.rsk==="CRITICAL"?"ESCALATED":s.rsk==="HIGH"?"MONITORING":"NORMAL"}
                    </span>
                  </div>
                </td>
                <td style={{padding:"8px 10px"}}>
                  {(s.rsk==="CRITICAL"||s.rsk==="HIGH")?(
                    <button style={{padding:"3px 10px",borderRadius:4,background:`${rsk2c(s.rsk)}20`,
                      border:`1px solid ${rsk2c(s.rsk)}60`,color:rsk2c(s.rsk),fontSize:9,cursor:"pointer",fontFamily:C.ffM,fontWeight:700}}>
                      REVIEW
                    </button>
                  ):<span style={{fontSize:9,color:C.t4,fontFamily:C.ffM}}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Supplier Risk Scores (higher = healthier)</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={riskBar} margin={{top:5,right:10,left:-20,bottom:20}}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.bg3}/>
              <XAxis dataKey="name" tick={{fill:C.t3,fontSize:9}} angle={-40} textAnchor="end"/>
              <YAxis tick={{fill:C.t3,fontSize:9}} domain={[0,100]}/>
              <Tooltip content={<Tip/>}/>
              <Bar dataKey="score" name="Risk Score">
                {riskBar.map((e,i)=><Cell key={i} fill={e.fill}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Volume at Risk by Risk Category</div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" nameKey="name">
                {pieData.map((e,i)=><Cell key={i} fill={e.col}/>)}
              </Pie>
              <Tooltip content={<Tip/>}/>
            </PieChart>
          </ResponsiveContainer>
          <div style={{display:"flex",justifyContent:"center",gap:14,flexWrap:"wrap",marginTop:4}}>
            {pieData.map(d=>(
              <span key={d.name} style={{display:"flex",alignItems:"center",gap:5,fontSize:9,color:C.t2,fontFamily:C.ffM}}>
                <span style={{width:10,height:10,borderRadius:2,background:d.col,display:"inline-block"}}/>
                {d.name}: {d.value.toFixed(0)}K
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// EVENT STREAM VIEW
// ═══════════════════════════════════════════════════════════
const EventStreamView=({events})=>{
  const [filter,setFilter]=useState("ALL");
  const types=["ALL","DISRUPTION","DECISION","ALERT","RISK","OPTIMIZATION","FORECAST","ESCALATION","UPDATE"];
  const filtered=filter==="ALL"?events:events.filter(e=>e.type===filter);
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <div style={{fontFamily:C.ffD,fontSize:13,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase"}}>Real-Time Event Intelligence Stream</div>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <Dot color={C.green} size={8}/>
            <span style={{fontSize:10,color:C.t2,fontFamily:C.ffM}}>LIVE · {events.length} events</span>
          </div>
        </div>
        <div style={{display:"flex",gap:7,flexWrap:"wrap"}}>
          {types.map(t=>(
            <button key={t} onClick={()=>setFilter(t)} style={{
              padding:"4px 10px",borderRadius:5,fontSize:9,cursor:"pointer",fontFamily:C.ffM,fontWeight:700,
              background:filter===t?`${C.sky}25`:"transparent",
              border:`1px solid ${filter===t?C.sky:C.bd1}`,
              color:filter===t?C.sky:C.t3,
              letterSpacing:"0.08em",textTransform:"uppercase"}}>
              {t}
            </button>
          ))}
        </div>
      </div>
      <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14,maxHeight:520,overflowY:"auto"}}>
        {filtered.map((e,i)=>(
          <div key={i} style={{display:"flex",gap:12,padding:"10px 14px",marginBottom:6,
            background:C.bg2,borderRadius:8,borderLeft:`3px solid ${sev2c(e.sev)}`}}>
            <div style={{minWidth:85}}>
              <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,marginBottom:4}}>{e.t||"--:--"}</div>
              <Chip label={e.type} color={sev2c(e.sev)}/>
            </div>
            <div style={{flex:1}}>
              <div style={{fontSize:11,color:C.t1,lineHeight:1.5}}>{e.msg}</div>
              <div style={{fontSize:9,color:C.t3,marginTop:4,fontFamily:C.ffM}}>→ {e.agent}</div>
            </div>
            <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:5}}>
              <Chip label={e.sev} color={sev2c(e.sev)}/>
              {e.sev==="CRITICAL"&&<Dot color={C.red} size={7}/>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// DIGITAL TWIN VIEW
// ═══════════════════════════════════════════════════════════
const DigitalTwinView=()=>{
  const [hov,setHov]=useState(null);
  const nodes=[
    {id:"S1",label:"Shenzhen",type:"supplier",rsk:"CRITICAL",x:652,y:145},
    {id:"S2",label:"Seoul",type:"supplier",rsk:"LOW",x:692,y:108},
    {id:"S3",label:"Tokyo",type:"supplier",rsk:"LOW",x:720,y:122},
    {id:"S4",label:"Munich",type:"supplier",rsk:"LOW",x:388,y:75},
    {id:"S5",label:"Bangalore",type:"supplier",rsk:"MEDIUM",x:547,y:158},
    {id:"S6",label:"Istanbul",type:"supplier",rsk:"MEDIUM",x:448,y:88},
    {id:"P1",label:"Shanghai Port",type:"port",x:670,y:158},
    {id:"P2",label:"Singapore Port",type:"port",x:633,y:200},
    {id:"P3",label:"Rotterdam",type:"port",x:406,y:82},
    {id:"P4",label:"LA Port",type:"port",x:133,y:128},
    {id:"P5",label:"Dubai Port",type:"port",x:513,y:147},
    {id:"W1",label:"Chicago",type:"warehouse",sts:"OPTIMAL",x:193,y:110},
    {id:"W2",label:"Dallas",type:"warehouse",sts:"CRITICAL",x:181,y:138},
    {id:"W3",label:"Frankfurt",type:"warehouse",sts:"WARNING",x:415,y:90},
    {id:"W4",label:"Singapore WH",type:"warehouse",sts:"WARNING",x:645,y:200},
    {id:"W5",label:"Dubai WH",type:"warehouse",sts:"OPTIMAL",x:522,y:150},
  ];
  const edges=[
    {f:"S1",t:"P1",act:true},{f:"S2",t:"P1",act:false},{f:"S3",t:"P1",act:false},
    {f:"P1",t:"P2",act:true},{f:"P2",t:"P4",act:true},{f:"P2",t:"W4",act:false},
    {f:"S4",t:"P3",act:false},{f:"S6",t:"P3",act:false},{f:"P3",t:"W3",act:false},
    {f:"P4",t:"W1",act:false},{f:"P4",t:"W2",act:true},{f:"S5",t:"P5",act:false},
    {f:"P5",t:"W5",act:false},
  ];
  const pos={};nodes.forEach(n=>{pos[n.id]={x:n.x,y:n.y};});
  const ncol=n=>n.type==="supplier"?rsk2c(n.rsk||"LOW"):n.type==="warehouse"?sts2c(n.sts||"OPTIMAL"):C.cyan;
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <div>
            <div style={{fontFamily:C.ffD,fontSize:13,fontWeight:700,letterSpacing:"0.08em",color:C.t1,textTransform:"uppercase"}}>Digital Twin — Live Supply Chain Topology</div>
            <div style={{fontSize:10,color:C.t3,fontFamily:C.ffM,marginTop:2}}>Real-time network state · Hover nodes for details</div>
          </div>
          <div style={{display:"flex",gap:12,fontSize:10,color:C.t2}}>
            {[["●",C.red,"Critical"],["●",C.amber,"Warning"],["●",C.green,"Optimal"],["▲",C.cyan,"Port"]].map(([ic,col,lb])=>(
              <span key={lb} style={{display:"flex",alignItems:"center",gap:4,fontFamily:C.ffM}}>
                <span style={{color:col}}>{ic}</span>{lb}
              </span>
            ))}
          </div>
        </div>
        <svg viewBox="0 0 800 300" style={{width:"100%",background:"#010a18",borderRadius:8}}>
          {Array.from({length:7},(_,i)=><line key={`h${i}`} x1="0" y1={i*50} x2="800" y2={i*50} stroke={C.bd1} strokeWidth="0.4" opacity="0.4"/>)}
          {Array.from({length:17},(_,i)=><line key={`v${i}`} x1={i*50} y1="0" x2={i*50} y2="300" stroke={C.bd1} strokeWidth="0.4" opacity="0.4"/>)}
          {edges.map((e,i)=>{const f=pos[e.f],t=pos[e.t];if(!f||!t)return null;return(
            <line key={i} x1={f.x} y1={f.y} x2={t.x} y2={t.y}
              stroke={e.act?C.sky:C.bd2} strokeWidth={e.act?2:0.8}
              strokeDasharray={e.act?"7 4":"none"} opacity={e.act?0.9:0.3}/>
          );})}
          {nodes.map(n=>{const c=ncol(n);return(
            <g key={n.id} onMouseEnter={()=>setHov(n)} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}>
              {n.type==="supplier"&&<><circle cx={n.x} cy={n.y} r={11} fill={c} opacity={0.15}/><circle cx={n.x} cy={n.y} r={5} fill={c} opacity={0.9}/></>}
              {n.type==="warehouse"&&<><rect x={n.x-8} y={n.y-8} width={16} height={16} fill={c} opacity={0.15}/><rect x={n.x-5} y={n.y-5} width={10} height={10} fill={c} opacity={0.9}/></>}
              {n.type==="port"&&<><polygon points={`${n.x},${n.y-8} ${n.x-6},${n.y+5} ${n.x+6},${n.y+5}`} fill={c} opacity={0.15}/><polygon points={`${n.x},${n.y-5} ${n.x-4},${n.y+3} ${n.x+4},${n.y+3}`} fill={c} opacity={0.9}/></>}
              <text x={n.x} y={n.y+17} textAnchor="middle" fill={C.t3} fontSize={7} fontFamily={C.ffM}>{n.label}</text>
            </g>
          );})}
          {hov&&(
            <foreignObject x={Math.min(hov.x+14,630)} y={hov.y-22} width={155} height={55}>
              <div style={{background:C.bg3,border:`1px solid ${C.bd2}`,borderRadius:6,padding:"6px 10px",fontFamily:C.ff}}>
                <div style={{fontSize:11,fontWeight:700,color:C.t1}}>{hov.label}</div>
                <div style={{fontSize:9,color:C.t2,fontFamily:C.ffM}}>
                  {hov.type.toUpperCase()}{hov.rsk&&` · ${hov.rsk} RISK`}{hov.sts&&` · ${hov.sts}`}
                </div>
              </div>
            </foreignObject>
          )}
        </svg>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:10}}>
        {[
          {label:"Total Nodes",val:"25",col:C.sky},
          {label:"Active Routes",val:"4",col:C.green},
          {label:"At-Risk Nodes",val:"3",col:C.red},
          {label:"Network Health",val:"78%",col:C.amber},
          {label:"Disrupted Paths",val:"5",col:C.red},
        ].map(s=>(
          <div key={s.label} style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:10,padding:"14px 16px"}}>
            <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:6}}>{s.label}</div>
            <div style={{fontSize:28,fontWeight:700,color:s.col,fontFamily:C.ffD}}>{s.val}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// AI COPILOT VIEW
// ═══════════════════════════════════════════════════════════
const SYS=`You are ARIA (Autonomous Route & Inventory Assistant), the AI Executive Copilot for an enterprise Supply Chain Control Tower. You have deep expertise in supply chain management, logistics optimization, inventory control, and risk assessment.

Current Platform State:
- 10 global suppliers across APAC/EMEA/LATAM/Americas
- 8 warehouses: Chicago (78%), Dallas CRITICAL (91%), Atlanta (64%), Seattle (55%), Frankfurt (82%), Amsterdam (71%), Singapore WH (88%), Dubai (67%)
- 3 ACTIVE DISRUPTIONS: Taiwan Strait restriction (CRITICAL), Typhoon Haikui (HIGH), Shenzhen factory shutdown (HIGH)
- OTIF: 87.3% (below 90% target) | Fill Rate: 94.2% | WH Utilization: 79% avg
- 8 AI agents active: Planner, Inventory, Logistics, Supplier Risk, Demand Forecasting, Escalation, KPI Monitor, Executive Summary
- Black Friday demand spike forecast: +340% in 30 days
- 2 decisions pending human approval ($8.7M threshold)
- Shenzhen Electronics (S001) risk score dropped to 32/100 — critical

Provide concise, actionable supply chain intelligence in an enterprise-grade tone. Use specific numbers. Be direct and decisive. Keep responses under 220 words unless detailed analysis is explicitly requested. Use **bold** for key metrics.`;

const CopilotView=()=>{
  const [msgs,setMsgs]=useState([
    {role:"assistant",content:"Good afternoon. I'm **ARIA**, your Supply Chain AI Copilot.\n\nCurrently monitoring **3 active disruptions** with OTIF at **87.3%** (below 90% target). Dallas DC is at **91% capacity** — critical threshold breached. Two decisions worth $8.7M are awaiting your approval.\n\nHow can I help you optimize operations today?"}
  ]);
  const [inp,setInp]=useState("");
  const [typing,setTyping]=useState(false);
  const chatRef=useRef(null);
  const QUICK=[
    "What are the top 3 risks right now?",
    "How should I respond to the Typhoon disruption?",
    "Explain the Dallas warehouse situation",
    "Black Friday readiness assessment?",
    "Summarize today's autonomous decisions",
    "Which suppliers should I review?",
  ];
  useEffect(()=>{if(chatRef.current)chatRef.current.scrollTop=chatRef.current.scrollHeight;},[msgs]);
  const send=async(text)=>{
    const m=text||inp.trim();if(!m||typing)return;
    setInp("");
    const next=[...msgs,{role:"user",content:m}];
    setMsgs(next);setTyping(true);
    try{
      const r=await fetch("https://api.anthropic.com/v1/messages",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({model:"claude-sonnet-4-20250514",max_tokens:1000,system:SYS,
          messages:next.map(x=>({role:x.role,content:x.content}))})
      });
      const d=await r.json();
      setMsgs(p=>[...p,{role:"assistant",content:d.content?.[0]?.text||"Unable to process."}]);
    }catch{
      setMsgs(p=>[...p,{role:"assistant",content:"Connection error. Please check your network."}]);
    }finally{setTyping(false);}
  };
  const fmtMsg=(txt)=>txt.split(/(\*\*[^*]+\*\*)/).map((p,i)=>
    p.startsWith("**")&&p.endsWith("**")
      ?<strong key={i} style={{color:C.sky}}>{p.slice(2,-2)}</strong>
      :p
  );
  return(
    <div style={{display:"flex",gap:12,height:"calc(100vh - 160px)"}}>
      <div style={{flex:1,display:"flex",flexDirection:"column",gap:10}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:"10px 14px",
          display:"flex",alignItems:"center",gap:10}}>
          <div style={{width:36,height:36,borderRadius:"50%",background:`${C.cyan}20`,border:`2px solid ${C.cyan}`,
            display:"flex",alignItems:"center",justifyContent:"center",fontSize:14}}>⬡</div>
          <div>
            <div style={{fontFamily:C.ffD,fontSize:14,fontWeight:700,color:C.cyan,letterSpacing:"0.05em"}}>ARIA — Supply Chain AI Copilot</div>
            <div style={{fontSize:10,color:C.t3,fontFamily:C.ffM}}>claude-sonnet-4 · Monitoring 3 disruptions · 8 agents active</div>
          </div>
          <div style={{marginLeft:"auto",display:"flex",gap:8}}>
            <Dot color={C.green} size={8}/><span style={{fontSize:10,color:C.t2,fontFamily:C.ffM}}>CONNECTED</span>
          </div>
        </div>
        <div ref={chatRef} style={{flex:1,overflowY:"auto",display:"flex",flexDirection:"column",gap:10}}>
          {msgs.map((m,i)=>(
            <div key={i} style={{display:"flex",gap:10,alignItems:"flex-start",flexDirection:m.role==="user"?"row-reverse":"row"}}>
              <div style={{width:30,height:30,borderRadius:"50%",flexShrink:0,
                background:m.role==="assistant"?`${C.cyan}20`:`${C.sky}20`,
                border:`1px solid ${m.role==="assistant"?C.cyan:C.sky}`,
                display:"flex",alignItems:"center",justifyContent:"center",fontSize:12}}>
                {m.role==="assistant"?"⬡":"◎"}
              </div>
              <div style={{maxWidth:"80%",background:m.role==="assistant"?C.bg2:C.bg3,
                border:`1px solid ${m.role==="assistant"?C.bd1:C.bd2}`,
                borderRadius:m.role==="assistant"?"4px 12px 12px 12px":"12px 4px 12px 12px",
                padding:"10px 14px",fontSize:13,color:C.t1,lineHeight:1.6,fontFamily:C.ff,
                whiteSpace:"pre-wrap"}}>
                {fmtMsg(m.content)}
              </div>
            </div>
          ))}
          {typing&&(
            <div style={{display:"flex",gap:10,alignItems:"flex-start"}}>
              <div style={{width:30,height:30,borderRadius:"50%",background:`${C.cyan}20`,
                border:`1px solid ${C.cyan}`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:12}}>⬡</div>
              <div style={{background:C.bg2,border:`1px solid ${C.bd1}`,borderRadius:"4px 12px 12px 12px",
                padding:"12px 16px",display:"flex",gap:6,alignItems:"center"}}>
                {[0,1,2].map(i=>(
                  <span key={i} style={{width:6,height:6,borderRadius:"50%",background:C.cyan,
                    animation:`pulse 1.2s ease-in-out ${i*0.2}s infinite`}}/>
                ))}
              </div>
            </div>
          )}
        </div>
        <div style={{display:"flex",gap:10}}>
          <input value={inp} onChange={e=>setInp(e.target.value)}
            onKeyDown={e=>e.key==="Enter"&&!e.shiftKey&&(e.preventDefault(),send())}
            placeholder="Ask ARIA about supply chain status, risks, or recommendations..."
            style={{flex:1,background:C.bg2,border:`1px solid ${C.bd2}`,borderRadius:8,
              padding:"10px 14px",color:C.t1,fontSize:12,fontFamily:C.ff,outline:"none"}}/>
          <button onClick={()=>send()} disabled={typing||!inp.trim()} style={{
            padding:"10px 20px",borderRadius:8,background:typing?C.bg3:`${C.sky}20`,
            border:`1px solid ${typing?C.bd1:C.sky}`,color:typing?C.t4:C.sky,
            fontSize:11,cursor:typing?"not-allowed":"pointer",fontFamily:C.ffM,fontWeight:700}}>
            {typing?"...":"SEND"}
          </button>
        </div>
      </div>
      <div style={{width:220,display:"flex",flexDirection:"column",gap:10}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14,flex:1}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.1em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Quick Actions</div>
          {QUICK.map((q,i)=>(
            <button key={i} onClick={()=>send(q)} style={{
              width:"100%",textAlign:"left",padding:"8px 10px",borderRadius:7,
              background:"transparent",border:`1px solid ${C.bd1}`,
              color:C.t2,fontSize:10,cursor:"pointer",fontFamily:C.ff,
              marginBottom:7,lineHeight:1.4,transition:"all 0.15s"}}>
              {q}
            </button>
          ))}
          <div style={{marginTop:14,padding:"10px 12px",background:C.bg2,borderRadius:8,border:`1px solid ${C.bd1}`}}>
            <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:8}}>System Context</div>
            {[["OTIF","87.3%",C.amber],["Disruptions","3 Active",C.red],["Decisions","2 Pending",C.amber],["Agents","8 Active",C.green]].map(([l,v,col])=>(
              <div key={l} style={{display:"flex",justifyContent:"space-between",padding:"4px 0",borderBottom:`1px solid ${C.bg3}`}}>
                <span style={{fontSize:10,color:C.t3}}>{l}</span>
                <span style={{fontSize:10,color:col,fontFamily:C.ffM,fontWeight:700}}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ANALYTICS VIEW
// ═══════════════════════════════════════════════════════════
const AnalyticsView=({kpis,kpi24h})=>{
  const radarData=[
    {metric:"OTIF",value:kpis.otif,benchmark:90},
    {metric:"Fill Rate",value:kpis.fill,benchmark:95},
    {metric:"Sup. Rel.",value:kpis.supRel,benchmark:92},
    {metric:"Delivery",value:100-kpis.delRisk,benchmark:85},
    {metric:"Stockout",value:100-kpis.stRisk,benchmark:97},
    {metric:"Inv. Turn",value:kpis.invTurn*12,benchmark:85},
  ];
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
        {[
          {label:"Total Shipments Active",val:"247",trend:"+12%",col:C.sky},
          {label:"Revenue at Risk",val:"$18.4M",trend:"+$3.2M",col:C.red},
          {label:"Cost Avoided (AI)",val:"$2.7M",trend:"+$450K",col:C.green},
          {label:"AI Decisions Today",val:"183",trend:"94.3% auto",col:C.purple},
        ].map(s=>(
          <div key={s.label} style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:10,padding:"14px 16px"}}>
            <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:8}}>{s.label}</div>
            <div style={{fontSize:26,fontWeight:700,color:s.col,fontFamily:C.ffD}}>{s.val}</div>
            <div style={{fontSize:10,color:C.t3,fontFamily:C.ffM,marginTop:5}}>{s.trend}</div>
          </div>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Operational KPI Scorecard</div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={kpi24h} margin={{top:5,right:5,left:-15,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.bg3}/>
              <XAxis dataKey="h" tick={{fill:C.t3,fontSize:8}} interval={5}/>
              <YAxis tick={{fill:C.t3,fontSize:8}} domain={[70,100]}/>
              <Tooltip content={<Tip/>}/>
              <Line type="monotone" dataKey="otif" stroke={C.amber} strokeWidth={2} dot={false} name="OTIF %"/>
              <Line type="monotone" dataKey="fill" stroke={C.green} strokeWidth={2} dot={false} name="Fill Rate %"/>
              <Line type="monotone" dataKey="util" stroke={C.sky} strokeWidth={2} dot={false} name="WH Util %"/>
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
          <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
            color:C.t1,textTransform:"uppercase",marginBottom:12}}>Performance vs Benchmark</div>
          <div style={{display:"flex",flexDirection:"column",gap:10,marginTop:8}}>
            {radarData.map(r=>{
              const pct=Math.min(r.value/r.benchmark*100,100);
              const col=pct>=100?C.green:pct>=90?C.sky:pct>=80?C.amber:C.red;
              return(
                <div key={r.metric}>
                  <div style={{display:"flex",justifyContent:"space-between",marginBottom:4,fontSize:10,fontFamily:C.ffM}}>
                    <span style={{color:C.t2}}>{r.metric}</span>
                    <span style={{color:col}}>{r.value.toFixed(1)} / {r.benchmark.toFixed(0)} <span style={{color:C.t4}}>benchmark</span></span>
                  </div>
                  <div style={{height:6,background:C.bg4,borderRadius:3}}>
                    <div style={{height:"100%",width:`${pct}%`,background:col,borderRadius:3,transition:"width 0.5s"}}/>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div style={{background:C.bg1,border:`1px solid ${C.bd1}`,borderRadius:12,padding:14}}>
        <div style={{fontFamily:C.ffD,fontSize:12,fontWeight:700,letterSpacing:"0.08em",
          color:C.t1,textTransform:"uppercase",marginBottom:12}}>AI Platform Performance</div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(6,1fr)",gap:10}}>
          {[
            {label:"Total AI Decisions",val:"2,847",col:C.sky},
            {label:"Auto-Approved",val:"94.3%",col:C.green},
            {label:"Avg Confidence",val:"91.2%",col:C.green},
            {label:"Cost Savings (MTD)",val:"$2.7M",col:C.cyan},
            {label:"Disruptions Mitigated",val:"18",col:C.purple},
            {label:"Human Escalations",val:"5.7%",col:C.amber},
          ].map(s=>(
            <div key={s.label} style={{background:C.bg2,borderRadius:8,padding:"12px",border:`1px solid ${C.bd1}`}}>
              <div style={{fontSize:8,color:C.t3,fontFamily:C.ffM,textTransform:"uppercase",marginBottom:6}}>{s.label}</div>
              <div style={{fontSize:20,fontWeight:700,color:s.col,fontFamily:C.ffD}}>{s.val}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════
const NAV=[
  {id:"dashboard",label:"Command Center",icon:"◉"},
  {id:"agents",label:"AI Agents",icon:"⬡"},
  {id:"twin",label:"Digital Twin",icon:"◈"},
  {id:"inventory",label:"Inventory",icon:"▣"},
  {id:"suppliers",label:"Supplier Risk",icon:"◆"},
  {id:"events",label:"Event Stream",icon:"≋"},
  {id:"copilot",label:"AI Copilot",icon:"◎"},
  {id:"analytics",label:"Analytics",icon:"▲"},
];

export default function App(){
  const [view,setView]=useState("dashboard");
  const [kpis,setKpis]=useState(genKPIs);
  const [events,setEvents]=useState(EVENTS_INIT);
  const [forecast]=useState(genForecast);
  const [kpi24h]=useState(genKPI24h);
  const [now,setNow]=useState(new Date());
  const [fontsLoaded,setFontsLoaded]=useState(false);

  // Font + style injection
  useEffect(()=>{
    const link=document.createElement("link");
    link.rel="stylesheet";
    link.href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=DM+Sans:wght@300;400;500;600;700&display=swap";
    document.head.appendChild(link);
    link.onload=()=>setFontsLoaded(true);
    const sty=document.createElement("style");
    sty.textContent=`
      *{box-sizing:border-box;margin:0;padding:0;}
      body{background:${C.bg0};color:${C.t1};}
      @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.35}}
      @keyframes slideIn{from{transform:translateX(-8px);opacity:0}to{transform:translateX(0);opacity:1}}
      ::-webkit-scrollbar{width:4px;height:4px}
      ::-webkit-scrollbar-track{background:${C.bg1}}
      ::-webkit-scrollbar-thumb{background:${C.bd2};border-radius:2px}
      button:hover{opacity:0.85}
      input:focus{border-color:${C.sky}!important}
    `;
    document.head.appendChild(sty);
    return()=>{document.head.removeChild(link);document.head.removeChild(sty);};
  },[]);

  // Real-time simulation
  useEffect(()=>{
    const interval=setInterval(()=>{
      setKpis(genKPIs());
      setNow(new Date());
      if(Math.random()<0.4){
        const ev=NEW_EVENTS_POOL[rndI(0,NEW_EVENTS_POOL.length)];
        const hrs=String(new Date().getHours()).padStart(2,"0");
        const min=String(new Date().getMinutes()).padStart(2,"0");
        setEvents(p=>[{...ev,t:`${hrs}:${min}`},...p.slice(0,29)]);
      }
    },5000);
    return()=>clearInterval(interval);
  },[]);

  const activeAgent=AGENTS.filter(a=>a.sts==="ACTIVE"||a.sts==="ALERT").length;

  return(
    <div style={{display:"flex",flexDirection:"column",height:"100vh",
      background:C.bg0,fontFamily:C.ff,overflow:"hidden"}}>
      {/* HEADER */}
      <div style={{height:56,background:C.bg1,borderBottom:`1px solid ${C.bd1}`,
        display:"flex",alignItems:"center",padding:"0 20px",gap:16,flexShrink:0}}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <div style={{width:34,height:34,borderRadius:8,background:`${C.sky}20`,
            border:`2px solid ${C.sky}`,display:"flex",alignItems:"center",
            justifyContent:"center",fontSize:16}}>◈</div>
          <div>
            <div style={{fontSize:14,fontWeight:700,color:C.sky,fontFamily:C.ffD,letterSpacing:"0.05em"}}>NEXUS CONTROL TOWER</div>
            <div style={{fontSize:9,color:C.t3,fontFamily:C.ffM,letterSpacing:"0.1em"}}>AUTONOMOUS SUPPLY CHAIN INTELLIGENCE PLATFORM</div>
          </div>
        </div>
        <div style={{marginLeft:"auto",display:"flex",alignItems:"center",gap:16}}>
          {/* Live KPI Ticker */}
          {[
            ["OTIF",kpis.otif+"%",kpis.otif<90?C.amber:C.green],
            ["FILL",kpis.fill+"%",C.green],
            ["AGENTS",activeAgent+"/8 ACTIVE",C.green],
          ].map(([l,v,col])=>(
            <div key={l} style={{display:"flex",alignItems:"center",gap:6,padding:"4px 10px",
              background:C.bg2,borderRadius:6,border:`1px solid ${C.bd1}`}}>
              <span style={{fontSize:9,color:C.t3,fontFamily:C.ffM}}>{l}</span>
              <span style={{fontSize:11,color:col,fontFamily:C.ffM,fontWeight:700}}>{v}</span>
            </div>
          ))}
          <div style={{display:"flex",alignItems:"center",gap:8,padding:"4px 12px",
            background:`${C.red}18`,border:`1px solid ${C.red}35`,borderRadius:6}}>
            <Dot color={C.red} size={7}/>
            <span style={{fontSize:10,color:C.red,fontFamily:C.ffM,fontWeight:700}}>3 DISRUPTIONS</span>
          </div>
          <div style={{fontSize:11,color:C.t3,fontFamily:C.ffM}}>
            {now.toLocaleDateString("en-US",{weekday:"short",month:"short",day:"numeric"})} {now.toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit"})}
          </div>
          <div style={{width:30,height:30,borderRadius:"50%",background:`${C.sky}20`,
            border:`1px solid ${C.sky}`,display:"flex",alignItems:"center",
            justifyContent:"center",fontSize:13,cursor:"pointer"}}>◎</div>
        </div>
      </div>

      {/* BODY */}
      <div style={{display:"flex",flex:1,overflow:"hidden"}}>
        {/* SIDEBAR */}
        <div style={{width:200,background:C.bg1,borderRight:`1px solid ${C.bd1}`,
          display:"flex",flexDirection:"column",padding:"12px 0",flexShrink:0}}>
          <div style={{padding:"0 14px 12px",fontSize:9,color:C.t4,fontFamily:C.ffM,
            letterSpacing:"0.12em",textTransform:"uppercase"}}>Navigation</div>
          {NAV.map(n=>(
            <button key={n.id} onClick={()=>setView(n.id)} style={{
              display:"flex",alignItems:"center",gap:10,padding:"9px 14px",
              background:view===n.id?`${C.sky}15`:"transparent",
              border:"none",borderLeft:view===n.id?`3px solid ${C.sky}`:"3px solid transparent",
              color:view===n.id?C.sky:C.t2,fontSize:12,cursor:"pointer",
              fontFamily:C.ff,fontWeight:view===n.id?600:400,
              width:"100%",textAlign:"left",transition:"all 0.15s"}}>
              <span style={{fontSize:13,color:view===n.id?C.sky:C.t3}}>{n.icon}</span>
              {n.label}
              {n.id==="events"&&<span style={{marginLeft:"auto",fontSize:9,color:C.red,fontFamily:C.ffM,fontWeight:700}}>{events.length}</span>}
              {n.id==="copilot"&&<span style={{marginLeft:"auto",fontSize:9,color:C.green,fontFamily:C.ffM}}>AI</span>}
            </button>
          ))}
          <div style={{marginTop:"auto",padding:"12px 14px",borderTop:`1px solid ${C.bd1}`}}>
            <div style={{fontSize:9,color:C.t4,fontFamily:C.ffM,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:8}}>System Status</div>
            {[["Kafka","STREAMING",C.green],["Redis","CONNECTED",C.green],["ML Engine","ACTIVE",C.green],["API Gateway","HEALTHY",C.green]].map(([n,s,col])=>(
              <div key={n} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"3px 0"}}>
                <span style={{fontSize:9,color:C.t3,fontFamily:C.ffM}}>{n}</span>
                <span style={{fontSize:8,color:col,fontFamily:C.ffM}}>{s}</span>
              </div>
            ))}
          </div>
        </div>

        {/* MAIN CONTENT */}
        <div style={{flex:1,overflowY:"auto",padding:16,background:C.bg0}}>
          {view==="dashboard"&&<DashboardView kpis={kpis} events={events} forecast={forecast} kpi24h={kpi24h}/>}
          {view==="agents"&&<AgentsView/>}
          {view==="twin"&&<DigitalTwinView/>}
          {view==="inventory"&&<InventoryView/>}
          {view==="suppliers"&&<SuppliersView/>}
          {view==="events"&&<EventStreamView events={events}/>}
          {view==="copilot"&&<CopilotView/>}
          {view==="analytics"&&<AnalyticsView kpis={kpis} kpi24h={kpi24h}/>}
        </div>
      </div>
    </div>
  );
}
