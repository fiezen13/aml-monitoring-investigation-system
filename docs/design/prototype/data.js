/* Mock data layer — Financial City AML (synthetic) */
function rng(seed){ let s=seed; return ()=>{ s=(s*1103515245+12345)%2147483648; return s/2147483648; }; }
const r = rng(42);
function pick(a){ return a[Math.floor(r()*a.length)]; }
function seq(n,f){ return Array.from({length:n},(_,i)=>f(i)); }
function money(v){ return v>=1e9?(v/1e9).toFixed(2)+'B':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v.toFixed(0); }

export const HUBS = [
  {id:'sg',name:'Singapore',lat:1.35,lon:103.8,size:3,vol:'2.4B',entities:48210,alerts:31},
  {id:'hk',name:'Hong Kong',lat:22.3,lon:114.2,size:3,vol:'1.9B',entities:39440,alerts:24},
  {id:'hn',name:'Hà Nội',lat:21.0,lon:105.85,size:2.4,vol:'860M',entities:22105,alerts:19},
  {id:'sgn',name:'TP.HCM',lat:10.78,lon:106.7,size:2.6,vol:'1.1B',entities:31280,alerts:27},
  {id:'bkk',name:'Bangkok',lat:13.75,lon:100.5,size:2,vol:'640M',entities:18730,alerts:9},
  {id:'mnl',name:'Manila',lat:14.6,lon:121.0,size:1.8,vol:'410M',entities:12490,alerts:14},
  {id:'pp',name:'Phnom Penh',lat:11.56,lon:104.9,size:1.6,vol:'380M',entities:8360,alerts:22},
  {id:'du',name:'Dubai',lat:25.2,lon:55.3,size:2.2,vol:'980M',entities:15920,alerts:11},
  {id:'ldn',name:'London',lat:51.5,lon:-0.12,size:2.6,vol:'1.6B',entities:28840,alerts:6},
  {id:'ny',name:'New York',lat:40.7,lon:-74.0,size:2.8,vol:'2.1B',entities:33110,alerts:5},
  {id:'tk',name:'Tokyo',lat:35.68,lon:139.7,size:2.2,vol:'1.2B',entities:21050,alerts:3},
  {id:'syd',name:'Sydney',lat:-33.87,lon:151.2,size:1.6,vol:'520M',entities:9870,alerts:2},
  {id:'fra',name:'Frankfurt',lat:50.1,lon:8.68,size:2,vol:'890M',entities:14260,alerts:4},
  {id:'lag',name:'Lagos',lat:6.45,lon:3.4,size:1.4,vol:'210M',entities:6120,alerts:8},
  {id:'sel',name:'Seoul',lat:37.56,lon:126.98,size:2,vol:'740M',entities:16480,alerts:4},
  {id:'sf',name:'San Francisco',lat:37.77,lon:-122.42,size:2,vol:'830M',entities:14210,alerts:3},
  {id:'sp',name:'São Paulo',lat:-23.55,lon:-46.63,size:1.8,vol:'480M',entities:11360,alerts:6},
];
const H = Object.fromEntries(HUBS.map(h=>[h.id,h]));
function flow(s,t,ch,risk,vol,txn,typ){ const a=H[s],b=H[t];
  return {sn:a.name,tn:b.name,slat:a.lat,slon:a.lon,tlat:b.lat,tlon:b.lon,ch,risk,vol,txn,typ,ph:r()}; }
export const FLOWS = [
  flow('pp','sgn','gamb','crit','12.4M',1842,'TYP-GMB-01 Gambling settlement'),
  flow('sgn','sg','p2p','crit','8.1M',926,'TYP-GMB-01 P2P → USDT'),
  flow('sg','hk','chain','warn','6.8M',312,'Cross-chain bridge (TRC20→ERC20)'),
  flow('hn','sgn','bank','warn','4.2M',2210,'TYP-FRD-02 mule fan-in'),
  flow('sgn','bkk','p2p','warn','2.9M',480,'P2P stablecoin off-ramp'),
  flow('hk','du','vasp','warn','5.5M',188,'VASP withdrawal cluster'),
  flow('mnl','pp','gamb','warn','1.8M',640,null),
  flow('sg','ldn','bank','ok','64M',5120,null), flow('ny','ldn','bank','ok','82M',6890,null),
  flow('tk','sg','bank','ok','31M',2380,null), flow('hk','sg','vasp','ok','18M',1240,null),
  flow('fra','ldn','bank','ok','44M',3610,null), flow('syd','sg','bank','ok','12M',980,null),
  flow('hn','hk','vasp','ok','7.2M',410,null), flow('bkk','sg','p2p','ok','3.4M',760,null),
  flow('du','ldn','bank','ok','26M',1520,null), flow('lag','du','p2p','warn','1.1M',290,'OTC corridor tăng bất thường'),
  flow('sgn','hk','chain','ok','9.6M',204,null), flow('ny','sg','chain','ok','15M',388,null),
  flow('mnl','sg','p2p','ok','2.2M',515,null), flow('pp','hk','proj','crit','3.7M',96,'TYP-TOK-03 token proceeds'),
  flow('hk','tk','proj','ok','4.1M',150,null),
  flow('sf','ny','bank','ok','38M',2940,null), flow('sel','tk','bank','ok','21M',1730,null),
  flow('sel','sg','vasp','ok','6.4M',360,null), flow('sf','sg','chain','ok','11M',270,null),
];
const CUR={bank:'USD · VND',p2p:'USDT',vasp:'USDT',chain:'USDT · ETH',gamb:'VND',proj:'TOKEN'};
HUBS.forEach(h=>{ h.inb=0; h.outb=0; h.cases=0; h.riskN=Math.min(96, 18+h.alerts*2.6); });
FLOWS.forEach((f,i)=>{ f.id='COR-'+String(i+1).padStart(3,'0'); f.cur=CUR[f.ch]||'USD';
  f.riskN=f.risk==='crit'?85+(i*7)%12:f.risk==='warn'?60+(i*5)%18:18+(i*11)%30;
  f.t0=((i*7)%21)/20; f.firstSeen=(2+(i*5)%22)+'h trước'; f.lastSeen=(2+(i*13)%55)+' phút trước';
  f.alertN=f.risk==='crit'?3+i%4:f.risk==='warn'?1+i%2:0;
  f.cases=f.risk==='crit'?['CASE-2026-0341']:(f.risk==='warn'&&i%2?['CASE-2026-0338']:[]);
  f.status=f.risk==='crit'?'ĐANG ĐIỀU TRA':f.risk==='warn'?'THEO DÕI':'BÌNH THƯỜNG';
  const s=HUBS.find(h=>h.name===f.sn), t=HUBS.find(h=>h.name===f.tn);
  if(s){ s.outb++; s.cases+=(f.cases||[]).length; } if(t){ t.inb++; t.cases+=(f.cases||[]).length; } });

export const TYPOLOGIES = [
  {id:'TYP-GMB-01', name:'Gambling – mule – USDT', color:'#FF4D61', count:34},
  {id:'TYP-FRD-02', name:'Fraud – P2P stablecoin', color:'#F5A524', count:27},
  {id:'TYP-TOK-03', name:'Junk token / rug pull', color:'#FF8A5C', count:12},
  {id:'TYP-CHN-04', name:'Cross-chain / mixer', color:'#A78BFA', count:18},
  {id:'TYP-OTC-05', name:'OTC / privacy asset', color:'#3185FF', count:9},
];

const VN_NAMES=['Trần Văn Hòa','Nguyễn Thị Mai','Lê Quốc Bảo','Phạm Minh Tuấn','Đỗ Thu Hằng','Vũ Đức Long','Hoàng Anh Dũng','Bùi Ngọc Lan','Đặng Văn Khánh','Ngô Thị Hương','Phan Tấn Phát','Lý Gia Hân'];
const BANKS=['VCB','TCB','MB','ACB','VPB','STB','BIDV'];
const STATUSES=['Mới','Đang điều tra','Chờ review','Đã xác nhận','False positive'];
const ANALYSTS=['L.T. Vy','N.H. Phúc','T.M. Châu','P.Q. Huy','— chưa gán —'];
function acct(){ return pick(BANKS)+' •'+String(1000+Math.floor(r()*9000)); }
function hash8(){ const c='0123456789abcdef'; return seq(8,()=>c[Math.floor(r()*16)]).join(''); }
export function walletAddr(){ return '0x'+hash8()+'…'+hash8().slice(0,4); }

export const ALERTS = seq(48,i=>{
  const typ=pick(TYPOLOGIES); const risk=Math.round(38+r()*60);
  const src=pick(['Rule Engine','Tabular ML','Graph Model','Crypto Tracer','Risk Fusion']);
  const etype=pick(['Account','Wallet','Organization','Person','Project']);
  return {
    id:'ALR-2026-'+String(4810-i).padStart(4,'0'),
    created: (i<4?['08:42','07:15','06:58','05:31'][i]:(Math.floor(i/3)+1)+' ngày trước'),
    entity: etype==='Person'?pick(VN_NAMES):etype==='Account'?acct():etype==='Wallet'?walletAddr():etype==='Project'?pick(['NovaFi Token','LUXP Protocol','MetaYield']):'CTCP '+pick(['Thanh Phát','Đại An','Kim Long','Hưng Thịnh']),
    etype, typ:typ.id, typName:typ.name,
    risk, conf: Math.round(55+r()*40)/100, src,
    rules: Math.floor(r()*6), graph: Math.round(r()*95), crypto: Math.round(r()*90),
    amount:'$'+money(20000+r()*4200000), evid: 2+Math.floor(r()*14),
    status: risk>82?'Chờ review':pick(STATUSES), analyst: risk>75?pick(ANALYSTS.slice(0,4)):pick(ANALYSTS),
    sla: risk>82?(Math.floor(r()*8)+1)+'h còn lại':'—',
  };
}).sort((a,b)=>b.risk-a.risk);

export const CASES = [
  {id:'CASE-2026-0341', scn:'SCN-01', name:'Đường dây gambling → mule → USDT', typ:'TYP-GMB-01', risk:94, conf:0.87, status:'Chờ human review',
   priority:'P1', analyst:'L.T. Vy', entities:26, rels:61, amount:'$12.4M', evid:23, evidDone:0.86, sla:'4h 12m', opened:'3 ngày trước',
   summary:'Cụm 14 tài khoản cá nhân mở mới trong 45 ngày nhận tiền tần suất cao từ nền tảng gambling ngoài lãnh thổ, fan-in về 2 tài khoản aggregator, chuyển đổi qua 3 P2P vendor thành USDT (TRC20) và hội tụ về 1 ví operator.',
   models:'RF v2.4.1 · GNN v1.9 · Rules 2026.07'},
  {id:'CASE-2026-0338', scn:'SCN-02', name:'Fraud victims → mule mới mở → P2P stablecoin', typ:'TYP-FRD-02', risk:88, conf:0.79, status:'Đang điều tra',
   priority:'P1', analyst:'N.H. Phúc', entities:19, rels:38, amount:'$3.1M', evid:15, evidDone:0.62, sla:'11h', opened:'2 ngày trước',
   summary:'11 nạn nhân lừa đảo chuyển tiền vào 6 tài khoản mule mở dưới 30 ngày; tiền chuyển tiếp qua P2P vendor thành stablecoin, đi multi-hop 4 lớp ví trước khi off-ramp tại VASP nước ngoài.',
   models:'RF v2.4.1 · GNN v1.9 · Rules 2026.07'},
  {id:'CASE-2026-0329', scn:'SCN-03', name:'Shell org → KOL promotion → rug pull LUXP', typ:'TYP-TOK-03', risk:81, conf:0.71, status:'Đang điều tra',
   priority:'P2', analyst:'T.M. Châu', entities:33, rels:74, amount:'$5.7M', evid:18, evidDone:0.54, sla:'1d 6h', opened:'5 ngày trước',
   summary:'Tổ chức shell phát hành token LUXP, thuê 8 kênh KOL quảng bá, wash trading tạo volume ảo 12 ngày, sau đó rút thanh khoản trong 34 phút và swap sang ETH → mixer.',
   models:'RF v2.4.1 · GNN v1.9 · TokenRisk v0.8'},
  {id:'CASE-2026-0322', scn:null, name:'Cluster OTC privacy asset — Lagos corridor', typ:'TYP-OTC-05', risk:66, conf:0.58, status:'Cần thêm thông tin',
   priority:'P3', analyst:'P.Q. Huy', entities:9, rels:14, amount:'$820K', evid:6, evidDone:0.31, sla:'—', opened:'8 ngày trước',
   summary:'Corridor OTC Lagos–Dubai tăng 240% trong 2 tuần; thiếu dữ liệu KYC phía đối tác.', models:'RF v2.4.1'},
  {id:'CASE-2026-0317', scn:null, name:'Bridge hopping qua 3 chain — ví cụm B', typ:'TYP-CHN-04', risk:59, conf:0.49, status:'False positive',
   priority:'P3', analyst:'L.T. Vy', entities:12, rels:20, amount:'$410K', evid:9, evidDone:1, sla:'—', opened:'12 ngày trước',
   summary:'Pattern bridge lặp được xác nhận là hoạt động arbitrage của market maker có đăng ký.', models:'GNN v1.9'},
];

// ===== SCN-01 deep data =====
// t = normalized appearance time (0 = T-45d, 1 = now); ev = evidence refs
export const SCN01 = {
  graph: {
    nodes: [
      {id:'plat', type:'platform', label:'LuckyStar88', sub:'gambling platform · offshore', risk:96, r:22, t:0, ev:['EV-204'], comm:'C1', first:'T-45d', last:'T-2d'},
      {id:'psp1', type:'platform', label:'PT-Gate', sub:'payment intermediary', risk:74, r:16, t:0.02, ev:['EV-204'], comm:'C1', first:'T-45d', last:'T-3d'},
      {id:'psp2', type:'platform', label:'FastPay88', sub:'payment intermediary', risk:71, r:16, t:0.05, ev:['EV-204'], comm:'C1', first:'T-44d', last:'T-4d'},
      {id:'pl1', type:'person', label:'Player pool A', sub:'~2.100 người chơi', risk:22, r:15, t:0, comm:'C1', first:'T-45d', last:'T-2d'},
      {id:'pl2', type:'person', label:'Player pool B', sub:'~1.400 người chơi', risk:20, r:14, t:0.03, comm:'C1', first:'T-44d', last:'T-3d'},
      {id:'m1',type:'account',label:'Mule 01',sub:'VCB •4821',risk:88,t:0.08,ev:['EV-201'],comm:'C2',first:'T-42d',last:'T-4d'},
      {id:'m2',type:'account',label:'Mule 02',sub:'TCB •7714',risk:86,t:0.09,ev:['EV-201'],comm:'C2',first:'T-42d',last:'T-5d'},
      {id:'m3',type:'account',label:'Mule 03',sub:'MB •2093',risk:85,t:0.10,ev:['EV-201'],comm:'C2',first:'T-41d',last:'T-4d'},
      {id:'m4',type:'account',label:'Mule 04',sub:'ACB •5570',risk:84,t:0.12,ev:['EV-201'],comm:'C2',first:'T-40d',last:'T-6d'},
      {id:'m5',type:'account',label:'Mule 05',sub:'VPB •8841',risk:83,t:0.13,ev:['EV-201'],comm:'C2',first:'T-40d',last:'T-5d'},
      {id:'m6',type:'account',label:'Mule 06',sub:'STB •1362',risk:82,t:0.15,ev:['EV-201'],comm:'C2',first:'T-39d',last:'T-7d'},
      {id:'m7',type:'account',label:'Mule 07',sub:'VCB •9917',risk:74,t:0.16,ev:['EV-201','EV-222'],comm:'C2',first:'T-39d',last:'T-6d'},
      {id:'m8',type:'account',label:'Mule 08',sub:'MB •3348',risk:80,t:0.18,ev:['EV-201'],comm:'C2',first:'T-38d',last:'T-8d'},
      {id:'m9',type:'account',label:'Mule 09',sub:'BIDV •7702',risk:79,t:0.30,ev:['EV-201'],comm:'C2',first:'T-30d',last:'T-9d'},
      {id:'m10',type:'account',label:'Mule 10',sub:'TCB •4419',risk:78,t:0.34,ev:['EV-201'],comm:'C2',first:'T-28d',last:'T-7d'},
      {id:'m11',type:'account',label:'Mule 11',sub:'ACB •8830',risk:77,t:0.42,ev:['EV-201'],comm:'C2',first:'T-24d',last:'T-6d'},
      {id:'m12',type:'account',label:'Mule 12',sub:'VPB •1195',risk:76,t:0.48,ev:['EV-201'],comm:'C2',first:'T-21d',last:'T-5d'},
      {id:'p1',type:'person',label:'T.V. Hòa',sub:'chủ TK Mule 01–03',risk:78,t:0.07,comm:'C2',first:'T-42d',last:'T-4d'},
      {id:'p2',type:'person',label:'N.T. Mai',sub:'chủ TK Mule 04–05',risk:74,t:0.11,comm:'C2',first:'T-40d',last:'T-5d'},
      {id:'p3',type:'person',label:'L.Q. Bảo',sub:'chủ TK Mule 09–12',risk:72,t:0.29,comm:'C2',first:'T-30d',last:'T-5d'},
      {id:'d1',type:'device',label:'Device A',sub:'IMEI …8812',risk:70,t:0.08,ev:['EV-211'],comm:'C2',first:'T-42d',last:'T-4d'},
      {id:'d2',type:'device',label:'Device B',sub:'IP 171.244.x.x',risk:68,t:0.10,ev:['EV-211'],comm:'C2',first:'T-41d',last:'T-5d'},
      {id:'d3',type:'device',label:'Device C',sub:'IP 113.161.x.x',risk:64,t:0.31,ev:['EV-211'],comm:'C2',first:'T-30d',last:'T-6d'},
      {id:'agg1',type:'account',label:'Aggregator 1',sub:'TCB •0044',risk:93,r:20,t:0.22,ev:['EV-209'],comm:'C3',first:'T-36d',last:'T-3d'},
      {id:'agg2',type:'account',label:'Aggregator 2',sub:'VCB •6103',risk:91,r:20,t:0.24,ev:['EV-209'],comm:'C3',first:'T-35d',last:'T-3d'},
      {id:'agg3',type:'account',label:'Aggregator 3',sub:'MB •5528',risk:87,r:18,t:0.52,ev:['EV-209'],comm:'C3',first:'T-19d',last:'T-4d'},
      {id:'v1',type:'person',label:'P2P Vendor A',sub:'Binance P2P',risk:76,t:0.55,ev:['EV-214'],comm:'C4',first:'T-18d',last:'T-3d'},
      {id:'v2',type:'person',label:'P2P Vendor B',sub:'OKX P2P',risk:72,t:0.57,ev:['EV-214'],comm:'C4',first:'T-17d',last:'T-3d'},
      {id:'v3',type:'person',label:'OTC Desk C',sub:'offline OTC',risk:79,t:0.60,ev:['EV-214'],comm:'C4',first:'T-16d',last:'T-4d'},
      {id:'vasp1',type:'platform',label:'VASP Exchange X',sub:'sàn nước ngoài',risk:66,r:18,t:0.62,comm:'C4',first:'T-15d',last:'T-2d'},
      {id:'va1',type:'account',label:'VASP acct #1',sub:'UID 41xx82',risk:74,t:0.63,comm:'C4',first:'T-15d',last:'T-3d'},
      {id:'va2',type:'account',label:'VASP acct #2',sub:'UID 55xx07',risk:71,t:0.66,comm:'C4',first:'T-14d',last:'T-3d'},
      {id:'w1',type:'wallet',label:'TX9f…c2a1',sub:'USDT TRC20',risk:82,t:0.70,ev:['EV-216'],comm:'C5',first:'T-13d',last:'T-2d'},
      {id:'w2',type:'wallet',label:'TQ3d…88be',sub:'USDT TRC20',risk:81,t:0.72,ev:['EV-216'],comm:'C5',first:'T-12d',last:'T-2d'},
      {id:'w3',type:'wallet',label:'TL5k…04fe',sub:'USDT TRC20',risk:80,t:0.74,ev:['EV-216'],comm:'C5',first:'T-12d',last:'T-3d'},
      {id:'w4',type:'wallet',label:'TB8n…31cc',sub:'USDT TRC20',risk:78,t:0.78,ev:['EV-216'],comm:'C5',first:'T-11d',last:'T-2d'},
      {id:'wop',type:'wallet',label:'OPERATOR',sub:'TR7m…d915',risk:96,r:23,t:0.84,ev:['EV-218'],comm:'C5',first:'T-9d',last:'T-1d'},
      {id:'sc1',type:'contract',label:'Swap router',sub:'0x7f…22ab',risk:58,t:0.88,comm:'C5',first:'T-6d',last:'T-2d'},
      {id:'ex1',type:'wallet',label:'Bridge ETH',sub:'0x4a…91f2',risk:64,t:0.90,comm:'C5',first:'T-5d',last:'T-1d'},
      {id:'tok1',type:'token',label:'USDT',sub:'TRC20 · asset',risk:12,r:13,t:0.70,comm:'C5',first:'T-13d',last:'T-1d'},
      {id:'org1',type:'org',label:'CTCP Thanh Phát',sub:'shell nghi vấn',risk:75,t:0.20,comm:'C3',first:'T-38d',last:'T-3d'},
      {id:'org2',type:'org',label:'CTCP Đại An',sub:'liên kết giám đốc',risk:61,t:0.25,comm:'C3',first:'T-34d',last:'T-6d'},
      {id:'mer1',type:'org',label:'Siêu thị Minh Long',sub:'merchant hợp pháp',risk:18,t:0.26,comm:'C6',first:'T-34d',last:'T-1d',negative:true},
      {id:'pay1',type:'account',label:'Payroll VPB •2210',sub:'TK lương công ty',risk:15,t:0.16,comm:'C6',first:'T-39d',last:'T-2d',negative:true},
      {id:'al1',type:'alert',label:'ALR-4801',sub:'fan-in velocity',risk:90,r:14,t:0.94,ev:['EV-220'],comm:'C3',first:'T-3d',last:'T-3d'},
      {id:'al2',type:'alert',label:'ALR-4788',sub:'crypto exposure',risk:84,r:13,t:0.86,comm:'C5',first:'T-8d',last:'T-8d'},
      {id:'case1',type:'case',label:'CASE-2026-0341',sub:'case container',risk:94,r:16,t:0.95,comm:'C3',first:'T-3d',last:'T-0'},
    ],
    edges: [
      {s:'pl1',t:'plat',kind:'transfer',label:'nạp $4.1M',amt:4100000,w:2,time:0.02,txns:'TXN-PL1-*  (12.480 rec)'},
      {s:'pl2',t:'plat',kind:'transfer',label:'nạp $2.6M',amt:2600000,w:1.8,time:0.04,txns:'TXN-PL2-* (7.910 rec)'},
      {s:'plat',t:'psp1',kind:'transfer',label:'settle $3.8M',amt:3800000,w:2,time:0.06,txns:'TXN-PSP1-* (2.140 rec)'},
      {s:'plat',t:'psp2',kind:'transfer',label:'settle $2.4M',amt:2400000,w:1.8,time:0.07,txns:'TXN-PSP2-* (1.680 rec)'},
      {s:'psp1',t:'m1',kind:'transfer',label:'$1.2M',amt:1200000,w:2,time:0.09,ev:'EV-204',txns:'TXN-A1..A612'},
      {s:'psp1',t:'m2',kind:'transfer',label:'$0.9M',amt:900000,w:1.8,time:0.10,ev:'EV-204',txns:'TXN-A613..A1104'},
      {s:'psp1',t:'m3',kind:'transfer',label:'$1.1M',amt:1100000,w:2,time:0.11,ev:'EV-204',txns:'TXN-A1105..A1702'},
      {s:'psp1',t:'m4',kind:'transfer',label:'$0.7M',amt:700000,w:1.5,time:0.13,ev:'EV-204'},
      {s:'psp2',t:'m5',kind:'transfer',label:'$0.8M',amt:800000,w:1.6,time:0.14,ev:'EV-204'},
      {s:'psp2',t:'m6',kind:'transfer',label:'$0.6M',amt:600000,w:1.4,time:0.16,ev:'EV-204'},
      {s:'psp2',t:'m7',kind:'transfer',label:'$0.5M',amt:500000,w:1.3,time:0.17,ev:'EV-204'},
      {s:'psp2',t:'m8',kind:'transfer',label:'$0.4M',amt:400000,w:1.2,time:0.19,ev:'EV-204'},
      {s:'psp1',t:'m9',kind:'transfer',label:'$0.5M',amt:500000,w:1.3,time:0.31},
      {s:'psp1',t:'m10',kind:'transfer',label:'$0.45M',amt:450000,w:1.2,time:0.35},
      {s:'psp2',t:'m11',kind:'transfer',label:'$0.38M',amt:380000,w:1.1,time:0.43},
      {s:'psp2',t:'m12',kind:'transfer',label:'$0.32M',amt:320000,w:1.1,time:0.49},
      {s:'p1',t:'m1',kind:'owns',label:'owns',time:0.07},{s:'p1',t:'m2',kind:'owns',label:'owns',time:0.08},
      {s:'p1',t:'m3',kind:'owns',label:'owns',time:0.09},{s:'p2',t:'m4',kind:'owns',label:'owns',time:0.12},
      {s:'p2',t:'m5',kind:'owns',label:'owns',time:0.13},{s:'p3',t:'m9',kind:'owns',label:'owns',time:0.30},
      {s:'p3',t:'m10',kind:'owns',label:'owns',time:0.34},{s:'p3',t:'m11',kind:'owns',label:'owns',time:0.42},
      {s:'p3',t:'m12',kind:'owns',label:'owns',time:0.48},
      {s:'d1',t:'m1',kind:'device',label:'shared device',inferred:true,conf:0.86,logic:'Cùng IMEI trong 41/43 phiên đăng nhập; khớp fingerprint trình duyệt.',time:0.09},
      {s:'d1',t:'m4',kind:'device',label:'shared device',inferred:true,conf:0.84,logic:'Cùng IMEI trong 18/20 phiên; khoảng cách thời gian trung bình 6 phút.',time:0.13},
      {s:'d1',t:'m6',kind:'device',label:'shared device',inferred:true,conf:0.79,logic:'Cùng IMEI trong 11/16 phiên.',time:0.16},
      {s:'d2',t:'m2',kind:'device',label:'shared IP',inferred:true,conf:0.71,logic:'Cùng IP tĩnh; không loại trừ được NAT của nhà mạng.',time:0.10},
      {s:'d2',t:'m7',kind:'device',label:'shared IP',inferred:true,conf:0.62,logic:'Cùng IP nhưng chỉ 4 phiên — bằng chứng yếu.',time:0.17},
      {s:'d2',t:'m8',kind:'device',label:'shared IP',inferred:true,conf:0.68,logic:'Cùng IP trong 9 phiên.',time:0.19},
      {s:'d3',t:'m9',kind:'device',label:'shared IP',inferred:true,conf:0.74,logic:'Cùng IP trong 14 phiên; cùng user-agent.',time:0.31},
      {s:'d3',t:'m10',kind:'device',label:'shared IP',inferred:true,conf:0.72,logic:'Cùng IP trong 12 phiên.',time:0.35},
      {s:'d3',t:'m12',kind:'device',label:'shared IP',inferred:true,conf:0.66,logic:'Cùng IP trong 7 phiên.',time:0.49},
      {s:'m1',t:'agg1',kind:'transfer',label:'$1.1M',amt:1100000,w:2,time:0.23,ev:'EV-209',txns:'TXN-B1..B208'},
      {s:'m2',t:'agg1',kind:'transfer',label:'$0.85M',amt:850000,w:1.7,time:0.24,ev:'EV-209'},
      {s:'m3',t:'agg1',kind:'transfer',label:'$1.0M',amt:1000000,w:1.9,time:0.25,ev:'EV-209'},
      {s:'m4',t:'agg2',kind:'transfer',label:'$0.65M',amt:650000,w:1.5,time:0.26,ev:'EV-209'},
      {s:'m5',t:'agg2',kind:'transfer',label:'$0.75M',amt:750000,w:1.6,time:0.27,ev:'EV-209'},
      {s:'m6',t:'agg2',kind:'transfer',label:'$0.55M',amt:550000,w:1.4,time:0.28,ev:'EV-209'},
      {s:'m7',t:'agg1',kind:'transfer',label:'$0.45M',amt:450000,w:1.2,time:0.29,ev:'EV-209'},
      {s:'m8',t:'agg2',kind:'transfer',label:'$0.35M',amt:350000,w:1.1,time:0.30,ev:'EV-209'},
      {s:'m9',t:'agg3',kind:'transfer',label:'$0.48M',amt:480000,w:1.3,time:0.53},
      {s:'m10',t:'agg3',kind:'transfer',label:'$0.42M',amt:420000,w:1.2,time:0.54},
      {s:'m11',t:'agg3',kind:'transfer',label:'$0.36M',amt:360000,w:1.1,time:0.55},
      {s:'m12',t:'agg3',kind:'transfer',label:'$0.30M',amt:300000,w:1.1,time:0.56},
      {s:'m3',t:'m5',kind:'transfer',label:'$28K (test)',amt:28000,w:0.9,time:0.32,txns:'TXN-CYC-01'},
      {s:'m5',t:'m3',kind:'transfer',label:'$28K (return)',amt:28000,w:0.9,time:0.33,txns:'TXN-CYC-02'},
      {s:'agg1',t:'v1',kind:'p2p',label:'P2P $1.9M',amt:1900000,w:2.2,time:0.58,ev:'EV-214',txns:'ORD-P2P-1..118'},
      {s:'agg1',t:'v2',kind:'p2p',label:'P2P $1.4M',amt:1400000,w:2,time:0.59,ev:'EV-214',txns:'ORD-P2P-119..214'},
      {s:'agg2',t:'v2',kind:'p2p',label:'P2P $0.9M',amt:900000,w:1.7,time:0.60,ev:'EV-214'},
      {s:'agg2',t:'v3',kind:'p2p',label:'OTC $1.3M',amt:1300000,w:2,time:0.61,ev:'EV-214'},
      {s:'agg3',t:'v3',kind:'p2p',label:'OTC $1.1M',amt:1100000,w:1.9,time:0.62},
      {s:'v1',t:'vasp1',kind:'deposit',label:'deposit',amt:1880000,w:2,time:0.63},
      {s:'v2',t:'vasp1',kind:'deposit',label:'deposit',amt:2270000,w:2.1,time:0.64},
      {s:'vasp1',t:'va1',kind:'owns',label:'hosts acct',time:0.63},
      {s:'vasp1',t:'va2',kind:'owns',label:'hosts acct',time:0.66},
      {s:'va1',t:'w1',kind:'withdrawal',label:'withdraw 1.88M',amt:1880000,w:2.2,time:0.70,ev:'EV-216'},
      {s:'va2',t:'w2',kind:'withdrawal',label:'withdraw 2.27M',amt:2270000,w:2.3,time:0.72,ev:'EV-216'},
      {s:'v3',t:'w3',kind:'crypto',label:'USDT 1.29M',amt:1290000,w:2,time:0.74,ev:'EV-216'},
      {s:'v3',t:'w4',kind:'crypto',label:'USDT 1.10M',amt:1100000,w:1.9,time:0.78},
      {s:'w1',t:'wop',kind:'crypto',label:'USDT 1.85M',amt:1850000,w:2.4,time:0.84,ev:'EV-218',txns:'0x91af…, 0x2b7c… (14 tx)'},
      {s:'w2',t:'wop',kind:'crypto',label:'USDT 2.25M',amt:2250000,w:2.5,time:0.85,ev:'EV-218'},
      {s:'w3',t:'wop',kind:'crypto',label:'USDT 1.27M',amt:1270000,w:2.2,time:0.85,ev:'EV-218'},
      {s:'w4',t:'wop',kind:'crypto',label:'USDT 1.08M',amt:1080000,w:2.1,time:0.86,ev:'EV-218'},
      {s:'w1',t:'tok1',kind:'asset',label:'asset',sourceOnly:true,time:0.70},
      {s:'wop',t:'tok1',kind:'asset',label:'asset',sourceOnly:true,time:0.84},
      {s:'wop',t:'sc1',kind:'swap',label:'swap $0.9M',amt:900000,w:1.7,time:0.88},
      {s:'sc1',t:'ex1',kind:'bridge',label:'bridge $0.6M',amt:600000,w:1.5,time:0.90},
      {s:'org1',t:'agg1',kind:'controls',label:'controls?',inferred:true,conf:0.52,logic:'Người đại diện đăng ký TK aggregator trùng cổ đông shell; chưa có xác nhận từ đăng ký doanh nghiệp.',time:0.22},
      {s:'org1',t:'plat',kind:'controls',label:'director link',inferred:true,conf:0.48,logic:'Giám đốc org1 xuất hiện trong hồ sơ tên miền nền tảng — nguồn OSINT, độ tin cậy thấp.',time:0.21},
      {s:'org2',t:'org1',kind:'director',label:'director of',inferred:true,conf:0.64,logic:'Cùng một cá nhân là giám đốc cả hai tổ chức theo dữ liệu đăng ký.',time:0.25},
      {s:'org1',t:'agg3',kind:'controls',label:'controls?',inferred:true,conf:0.44,logic:'Trùng số điện thoại liên hệ; chưa xác minh.',time:0.52},
      {s:'al1',t:'agg1',kind:'alert',label:'triggered on',time:0.94},
      {s:'al2',t:'wop',kind:'alert',label:'triggered on',time:0.86},
      {s:'case1',t:'al1',kind:'member',label:'member of case',time:0.95},
      {s:'case1',t:'al2',kind:'member',label:'member of case',time:0.95},
      {s:'case1',t:'agg1',kind:'member',label:'member of case',time:0.95},
      {s:'case1',t:'wop',kind:'member',label:'member of case',time:0.95},
      {s:'m7',t:'pay1',kind:'transfer',label:'lương $2.1K/tháng',amt:2100,w:0.8,time:0.17,txns:'TXN-PAY-*'},
      {s:'pay1',t:'m7',kind:'transfer',label:'lương vào $2.1K',amt:2100,w:0.8,time:0.18,txns:'TXN-PAY-IN-*'},
      {s:'m6',t:'mer1',kind:'transfer',label:'chi tiêu $8.4K',amt:8400,w:0.8,time:0.27,txns:'TXN-MER-*'},
      {s:'m2',t:'mer1',kind:'transfer',label:'chi tiêu $3.2K',amt:3200,w:0.8,time:0.26},
      {s:'mer1',t:'agg2',kind:'transfer',label:'thanh toán NCC $46K',amt:46000,w:1,time:0.30,txns:'TXN-MER-SUP-*'},
      {s:'d2',t:'pay1',kind:'device',label:'shared IP',inferred:true,conf:0.31,logic:'Cùng IP nhưng là IP văn phòng dùng chung — khả năng cao là trùng hợp (hard negative).',time:0.18},
    ],
    moneyPath: ['pl1','plat','psp1','m1','agg1','v1','vasp1','va1','w1','wop'],
    paths: [
      {id:'P1', nodes:['plat','psp1','m1','agg1','v1','vasp1','va1','w1','wop'], amt:'$1.85M', hops:8, dur:'34 ngày', ch:'bank → P2P → VASP → crypto', score:0.94},
      {id:'P2', nodes:['plat','psp1','m3','agg1','v2','vasp1','va2','w2','wop'], amt:'$1.62M', hops:8, dur:'31 ngày', ch:'bank → P2P → VASP → crypto', score:0.91},
      {id:'P3', nodes:['plat','psp2','m5','agg2','v3','w3','wop'], amt:'$1.27M', hops:6, dur:'27 ngày', ch:'bank → OTC → crypto', score:0.88},
      {id:'P4', nodes:['plat','psp1','m9','agg3','v3','w4','wop'], amt:'$1.08M', hops:6, dur:'19 ngày', ch:'bank → OTC → crypto', score:0.81},
    ],
    cycles: [
      {id:'CY1', nodes:['m3','m5','m3'], len:2, amt:'$28K', cons:'100% (bảo toàn)', first:'T-32d 09:14', last:'T-31d 10:02', note:'Khả năng test transaction giữa 2 mule cùng cụm thiết bị.'},
      {id:'CY2', nodes:['m2','mer1','agg2','agg1','m2'], len:4, amt:'$3.2K', cons:'7% (không bảo toàn)', first:'T-34d', last:'T-30d', note:'Đi qua merchant hợp pháp — khả năng cao là trùng hợp, không phải chu trình rửa tiền.'},
    ],
    communities: [
      {id:'C1', name:'Nguồn gambling', color:'#F5A524', n:5},
      {id:'C2', name:'Cụm mule + thiết bị', color:'#3185FF', n:19},
      {id:'C3', name:'Aggregator & shell org', color:'#A78BFA', n:8},
      {id:'C4', name:'P2P / OTC / VASP', color:'#12D6C5', n:6},
      {id:'C5', name:'Ví crypto', color:'#2DD4A7', n:9},
      {id:'C6', name:'Hard negative (hợp pháp)', color:'#607487', n:2},
    ],
  },
  timeline: [
    {t:'T-45d', title:'8 tài khoản mule mở mới', d:'Mở tại 6 ngân hàng trong 9 ngày, cùng 2 cụm thiết bị/IP', kind:'fact', ev:'EV-201'},
    {t:'T-38d', title:'Settlement gambling bắt đầu', d:'LuckyStar88 chi trả tần suất 40–80 giao dịch/ngày/TK, giá trị 3–18 triệu VND', kind:'fact', ev:'EV-204'},
    {t:'T-21d', title:'Fan-in về aggregator', d:'92% dòng ra của 8 mule hội tụ về 2 tài khoản trong ≤ 2 hop', kind:'fact', ev:'EV-209'},
    {t:'T-14d', title:'Chuyển đổi P2P/OTC', d:'3 vendor thực hiện 214 lệnh mua USDT khớp thời gian ±15 phút với dòng ra aggregator', kind:'fact', ev:'EV-214'},
    {t:'T-9d', title:'Hội tụ ví operator', d:'3 ví trung gian chuyển 96% số dư về TR7m…d915 trong 48h', kind:'fact', ev:'EV-218'},
    {t:'T-3d', title:'Alert ALR-4801 sinh bởi Graph Model', d:'Fan-in velocity + community detection score 0.94', kind:'system', ev:'EV-220'},
    {t:'T-2d', title:'AI Agent hoàn tất draft report', d:'QA validation pass 14/15 claim; 1 claim bị reject do thiếu evidence', kind:'system', ev:'—'},
    {t:'T-0', title:'Chờ human review', d:'Analyst L.T. Vy đang review; SLA còn 4h 12m', kind:'review', ev:'—'},
  ],
  evidence: [
    {id:'EV-201', kind:'FACT', src:'query_bank_transactions', claim:'8 tài khoản mở mới trong cửa sổ 9 ngày (12/06–21/06), cùng chi nhánh đăng ký online', conf:null, hash:'a91f3c02'},
    {id:'EV-204', kind:'FACT', src:'query_bank_transactions', claim:'Tổng 6.240 giao dịch nhận từ 3 trung gian thanh toán của LuckyStar88, tổng $6.2M trong 38 ngày', conf:null, hash:'bb27e910'},
    {id:'EV-209', kind:'FACT', src:'graph_neighbors', claim:'Fan-in ratio 0.92 về AGG-1/AGG-2; cấu trúc star 2 lớp', conf:null, hash:'c3d80a44'},
    {id:'EV-211', kind:'INFERENCE', src:'get_account_features', claim:'2 cụm thiết bị dùng chung gợi ý cùng một nhóm điều phối vận hành 8 tài khoản', conf:0.81, hash:'d40c1f7e'},
    {id:'EV-214', kind:'FACT', src:'get_p2p_orders', claim:'214 lệnh P2P mua USDT khớp ±15 phút, chênh lệch giá trị <3% so với dòng ra aggregator', conf:null, hash:'e88b2c19'},
    {id:'EV-216', kind:'INFERENCE', src:'get_crypto_flows', claim:'Ví TR7m…d915 có hành vi consolidate đặc trưng operator (nhận từ ≥3 nguồn, chu kỳ 48h)', conf:0.77, hash:'f19a0d55'},
    {id:'EV-218', kind:'FACT', src:'get_crypto_flows', claim:'96% số dư 3 ví trung gian chuyển về TR7m…d915 trong 48h (14–16/07)', conf:null, hash:'0a6e44b1'},
    {id:'EV-220', kind:'FACT', src:'get_model_explanation', claim:'GNN v1.9: community score 0.94, top features: fanin_velocity, new_account_ratio, p2p_timing_corr', conf:null, hash:'1b7f55c2'},
    {id:'EV-222', kind:'CONTRA', src:'compare_peer_group', claim:'Mule 07 có lịch sử lương đều 14 tháng trước — không khớp profile mule thuần túy', conf:null, hash:'2c8a66d3'},
  ],
  alternatives: [
    'Đại lý thanh toán hộ (payment agent) cho nền tảng game hợp pháp chưa đăng ký — cần kiểm tra hợp đồng đại lý.',
    'Hoạt động OTC arbitrage USDT tận dụng chênh lệch giá P2P — không giải thích được cấu trúc device-sharing.',
  ],
  missing: [
    'KYC gốc của 3 P2P vendor (đã gửi request_more_data tới VASP — chờ 2/3 phản hồi)',
    'Sao kê đối ứng của trung gian thanh toán PT-Gate (ngoài phạm vi dữ liệu hiện có)',
    'Danh tính chủ sở hữu hưởng lợi CTCP Thanh Phát (đang chờ đăng ký doanh nghiệp)',
  ],
  checklist: [
    {t:'Xác minh cụm thiết bị dùng chung', done:true},{t:'Đối chiếu timing P2P với dòng ra aggregator', done:true},
    {t:'Truy vết hội tụ ví operator', done:true},{t:'Kiểm tra alternative: payment agent hợp pháp', done:true},
    {t:'Thu thập KYC P2P vendor', done:false},{t:'Xác minh beneficial owner CTCP Thanh Phát', done:false},
  ],
  fusion: [
    {label:'Rule score', value:22, color:'#3185FF', sub:'6 rule hits'},
    {label:'Tabular ML', value:18, color:'#12D6C5', sub:'RF v2.4.1 · p=0.91'},
    {label:'Graph score', value:27, color:'#A78BFA', sub:'GNN v1.9 · 0.94'},
    {label:'Crypto exposure', value:16, color:'#2DD4A7', sub:'operator wallet direct'},
    {label:'Project risk', value:3, color:'#FF8A5C', sub:'không liên quan token'},
    {label:'Policy adjust', value:8, color:'#F5A524', sub:'corridor PP→SGN +8'},
  ],
};

export const AGENT_RUN = {
  id:'RUN-2026-1187', caseId:'CASE-2026-0341', state:'HUMAN REVIEW', started:'T-2d 14:05', runtime:'8m 42s',
  reviewer:'L.T. Vy', model:'InvestigatorAgent v3.2 · QA v1.4',
  plan: [
    'Triage alert ALR-4801 và xác định phạm vi entity ban đầu',
    'Thu thập giao dịch bank 45 ngày của cụm nghi vấn',
    'Phân tích cấu trúc graph: fan-in, community, device sharing',
    'Đối chiếu lệnh P2P và dòng crypto đến ví hội tụ',
    'Kiểm tra alternative explanations và peer group',
    'Soạn draft report với claim–evidence matrix',
  ],
  states:['INIT','TRIAGE','PLAN READY','COLLECTING EVIDENCE','HYPOTHESIS CHECK','MORE DATA REQUIRED','DRAFT READY','QA VALIDATION','HUMAN REVIEW'],
  stateIdx:8,
  tools: [
    {tool:'get_case', input:'CASE-2026-0341', dur:'0.4s', results:1, ev:null, status:'ok', out:'{ case, 3 linked alerts, 26 entities }'},
    {tool:'get_entity_profile', input:'AGG-1 (TCB •0044)', dur:'0.8s', results:1, ev:null, status:'ok', out:'{ kyc_age: 145d, turnover_30d: $3.4M, peer_pct: 99.7 }'},
    {tool:'query_bank_transactions', input:'8 mule accounts · window 45d', dur:'2.1s', results:6240, ev:'EV-201, EV-204', status:'ok', out:'{ txns: 6240, total: $6.2M, sources: 3 PSP }'},
    {tool:'get_account_features', input:'device & IP clusters', dur:'1.2s', results:2, ev:'EV-211', status:'ok', out:'{ clusters: [Device A: 3 accts, Device B: 3 accts] }'},
    {tool:'graph_neighbors', input:'AGG-1, AGG-2 · k=2', dur:'1.6s', results:61, ev:'EV-209', status:'ok', out:'{ nodes: 26, edges: 61, fanin: 0.92 }'},
    {tool:'find_money_paths', input:'plat → wop · max 6 hop', dur:'2.8s', results:14, ev:'EV-218', status:'ok', out:'{ paths: 14, dominant: 5-hop qua AGG-1 }'},
    {tool:'get_p2p_orders', input:'3 vendors · window 21d', dur:'1.4s', results:214, ev:'EV-214', status:'ok', out:'{ orders: 214, timing_corr: 0.91 }'},
    {tool:'get_crypto_flows', input:'w1,w2,w3 → consolidation', dur:'1.9s', results:38, ev:'EV-216, EV-218', status:'ok', out:'{ consolidation: 96% → TR7m…d915 }'},
    {tool:'compare_peer_group', input:'Mule 07 vs cohort', dur:'0.9s', results:1, ev:'EV-222', status:'warn', out:'{ anomaly: salary history 14mo — conflicting }'},
    {tool:'request_more_data', input:'KYC 3 P2P vendors → VASP', dur:'0.3s', results:0, ev:null, status:'pending', out:'{ requests: 3, responded: 1 }'},
    {tool:'get_model_explanation', input:'GNN v1.9 · ALR-4801', dur:'0.7s', results:1, ev:'EV-220', status:'ok', out:'{ score: 0.94, top_features: [...] }'},
    {tool:'submit_draft_report', input:'15 claims · 9 evidence', dur:'1.1s', results:1, ev:null, status:'ok', out:'{ qa: 14/15 pass, 1 rejected }'},
  ],
  qa: [{claim:'“Toàn bộ 8 tài khoản do một cá nhân điều phối”', verdict:'REJECTED', reason:'Chỉ có evidence device-sharing cho 6/8 tài khoản. Đã hạ xuống inference với confidence 0.81.'}],
  report: {
    exec:'Cụm 26 entity thể hiện typology TYP-GMB-01 (Gambling – mule – USDT) với mức tin cậy cao. Dòng tiền $6.2M từ nền tảng LuckyStar88 qua 8 tài khoản mule → 2 aggregator → 3 P2P/OTC vendor → hội tụ 96% về ví TR7m…d915. Khuyến nghị: chuyển human review xác nhận và cân nhắc lập STR. Hệ thống KHÔNG tự kết luận hành vi phạm tội — quyết định thuộc về chuyên viên.',
    facts:['6.240 giao dịch nhận từ PSP của LuckyStar88, tổng $6.2M/38 ngày (EV-204)','Fan-in ratio 0.92 về 2 aggregator (EV-209)','214 lệnh P2P khớp timing ±15 phút (EV-214)','96% số dư hội tụ về ví operator trong 48h (EV-218)'],
    inferences:[{t:'Cụm thiết bị chung → một nhóm điều phối vận hành ≥6 tài khoản', c:0.81},{t:'TR7m…d915 là ví operator của nền tảng gambling', c:0.77},{t:'CTCP Thanh Phát có liên hệ điều hành với LuckyStar88', c:0.52}],
    contra:['Mule 07 có lịch sử lương ổn định 14 tháng (EV-222) — có thể là tài khoản bị thuê/mượn thay vì mở mới chuyên dụng'],
    next:['Chờ KYC từ 2 VASP còn lại','Xác minh beneficial owner CTCP Thanh Phát','Nếu xác nhận: lập STR và thông báo đơn vị giám sát'],
  },
};

export const FEED_TEMPLATES = [
  {k:'alert', t:'Alert mới {id} · fan-in velocity · risk {r}'},
  {k:'agent', t:'Agent bắt đầu điều tra {id}'},
  {k:'evid', t:'Evidence {ev} thu thập từ get_crypto_flows'},
  {k:'qa', t:'QA reject 1 claim trong {id} — thiếu evidence'},
  {k:'human', t:'Analyst xác nhận case {id} là suspicious'},
  {k:'model', t:'Model GNN v1.9 → v1.9.1 (shadow mode)'},
  {k:'pipe', t:'Pipeline P2P orders trễ 4 phút — đang bù'},
  {k:'txn', t:'Corridor PP→SGN: spike 2.1x baseline 15 phút'},
];

export const TXNS = seq(40,i=>{
  const ch=pick(['Bank','Bank','Bank','P2P','VASP','On-chain','Gambling']);
  const risk=Math.round(r()*100);
  return { id:'TXN-'+hash8().toUpperCase(), time:'08:'+String(59-i).padStart(2,'0'),
    from: ch==='On-chain'?walletAddr():acct(), to: ch==='On-chain'?walletAddr():(r()>0.5?acct():walletAddr()),
    ch, amount:'$'+money(500+r()*900000), cur: ch==='On-chain'?'USDT':pick(['VND','VND','USD']),
    risk, flags: risk>80?pick(['fan-in','velocity','structuring','new-account']):risk>60?pick(['timing-corr','round-amount','—']):'—' };
});

export const PROJECTS = [
  {name:'LUXP Protocol', chain:'BSC', risk:91, liq:'−98% (34 phút)', holders:'4.210 → 380', wash:'0.86', kol:8, status:'CASE-2026-0329'},
  {name:'NovaFi Token', chain:'Ethereum', risk:74, liq:'−41% (7 ngày)', holders:'12.400 → 9.100', wash:'0.61', kol:3, status:'Đang theo dõi'},
  {name:'MetaYield', chain:'Polygon', risk:58, liq:'ổn định', holders:'8.220 (+2%)', wash:'0.44', kol:5, status:'Watchlist'},
  {name:'GreenDAO', chain:'Ethereum', risk:22, liq:'ổn định', holders:'31.050 (+6%)', wash:'0.08', kol:1, status:'—'},
];

export const MODELS = [
  {name:'RF Tabular v2.4.1', kind:'Tabular ML', auc:0.941, drift:0.021, status:'Healthy', last:'2h trước', pred:'1.2M/ngày'},
  {name:'GNN v1.9', kind:'Graph Model', auc:0.928, drift:0.034, status:'Healthy', last:'2h trước', pred:'340K/ngày'},
  {name:'GNN v1.9.1', kind:'Graph Model (shadow)', auc:0.933, drift:0.019, status:'Shadow', last:'2h trước', pred:'340K/ngày'},
  {name:'CryptoTracer v1.2', kind:'Crypto heuristics', auc:0.902, drift:0.058, status:'Watch drift', last:'4h trước', pred:'88K/ngày'},
  {name:'TokenRisk v0.8', kind:'Project risk', auc:0.874, drift:0.012, status:'Beta', last:'1d trước', pred:'2.1K/ngày'},
];

export const DQ = [
  {src:'Core banking txn', fresh:'42s', comp:99.8, dup:0.02, schema:'OK', status:'ok'},
  {src:'P2P order feed', fresh:'4m 12s', comp:97.1, dup:0.4, schema:'OK', status:'warn'},
  {src:'VASP reports', fresh:'18m', comp:92.4, dup:0.1, schema:'OK', status:'warn'},
  {src:'On-chain indexer', fresh:'12s', comp:99.9, dup:0, schema:'OK', status:'ok'},
  {src:'KYC registry', fresh:'1h 02m', comp:88.6, dup:1.2, schema:'2 cột thiếu', status:'crit'},
  {src:'Gambling intel', fresh:'26m', comp:94.0, dup:0.3, schema:'OK', status:'ok'},
];

export const AUDIT = seq(22,i=>{
  const acts=[['L.T. Vy','xem case CASE-2026-0341','READ'],['N.H. Phúc','cập nhật status ALR-4788 → Đang điều tra','WRITE'],['system','Agent RUN-2026-1187 submit draft','AGENT'],['T.M. Châu','export báo cáo CASE-2026-0329 (mock)','EXPORT'],['P.Q. Huy','bulk assign 6 alerts → N.H. Phúc','WRITE'],['admin','đổi ngưỡng rule R-114: 50M → 45M VND','CONFIG'],['L.T. Vy','xác nhận suspicious CASE-2026-0335 · lý do: cấu trúc fan-in','DECISION'],['system','model GNN v1.9.1 deploy shadow','SYSTEM']];
  const a=acts[i%acts.length];
  return {time:'0'+(8-Math.floor(i/8))+':'+String(58-i*2%60).padStart(2,'0'), user:a[0], action:a[1], kind:a[2], ip:'10.30.'+Math.floor(r()*99)+'.'+Math.floor(r()*200)};
});

export const BENCH = {
  precisionK: seq(10,i=>({k:(i+1)*10, v: 0.95-i*0.038+(r()-0.5)*0.02})),
  recall: [{label:'Case-level recall', value:0.83},{label:'Alert-level recall', value:0.71},{label:'Typology coverage', value:0.9}],
  fpr: seq(12,i=>34-i*1.4+(r()-0.5)*3),
  invTime: seq(12,i=>96-i*4.8+(r()-0.5)*8),
  baseline:[{label:'Rule-only baseline', p:0.31, note:'precision@100'},{label:'Rules + Tabular ML', p:0.52, note:'precision@100'},{label:'+ Graph Model', p:0.71, note:'precision@100'},{label:'+ Crypto & Fusion (hiện tại)', p:0.84, note:'precision@100'}],
};

export function makeSeries(n, base, vol, trend=0){ let v=base; return seq(n,i=>{ v=Math.max(0, v+(r()-0.48)*vol+trend); return Math.round(v*10)/10; }); }
export const OV = {
  hours: seq(24,i=>String(i).padStart(2,'0')+'h'),
  days: seq(30,i=>'T'+(i+1)),
  riskVol: makeSeries(30, 420, 60, 2),
  alertsBySev: { labels: seq(14,i=>['T2','T3','T4','T5','T6','T7','CN'][i%7]),
    crit: makeSeries(14, 8, 4), high: makeSeries(14, 21, 8), med: makeSeries(14, 46, 14) },
  convRate: makeSeries(12, 34, 5, 0.4), fpRate: makeSeries(12, 28, 4, -0.8),
  heat: seq(7,()=>seq(24,()=>Math.round(r()*r()*100))),
  velocity: makeSeries(48, 1200, 260),
  corridors: [
    {label:'Phnom Penh → TP.HCM', value:12.4, color:'#FF4D61', sub:'gambling settlement · 2.1x baseline'},
    {label:'TP.HCM → Singapore', value:8.1, color:'#F5A524', sub:'P2P → USDT'},
    {label:'Hà Nội → TP.HCM', value:4.2, color:'#F5A524', sub:'mule fan-in'},
    {label:'Hong Kong → Dubai', value:5.5, color:'#3185FF', sub:'VASP withdrawal'},
    {label:'Lagos → Dubai', value:1.1, color:'#3185FF', sub:'OTC corridor'},
  ],
};
