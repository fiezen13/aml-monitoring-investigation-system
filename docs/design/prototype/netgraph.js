/* fc-graph: AML investigation graph engine (canvas) — typed node shapes, risk encoding, path/cycle/community analysis */
(() => {
if (customElements.get('fc-graph')) return;
const TYPE = {
  person:{c:'#3185FF',shape:'circle',name:'Person',g:'P'},
  org:{c:'#A78BFA',shape:'rrect',name:'Organization',g:'O'},
  account:{c:'#12D6C5',shape:'rect',name:'Account',g:'A'},
  device:{c:'#607487',shape:'hex',name:'Device',g:'D'},
  wallet:{c:'#2DD4A7',shape:'diamond',name:'Wallet',g:'W'},
  project:{c:'#FF8A5C',shape:'rrect-lg',name:'Project',g:'T'},
  token:{c:'#8FA4B8',shape:'pill',name:'Token',g:'$'},
  contract:{c:'#F5A524',shape:'diamond2',name:'Smart contract',g:'C'},
  platform:{c:'#91A4B5',shape:'octagon',name:'Platform',g:'X'},
  alert:{c:'#FF4D61',shape:'warning',name:'Alert',g:'!'},
  case:{c:'#FF6B7C',shape:'container',name:'Case',g:'K'},
};
const EDGE_LABEL = {transfer:'Transferred to',owns:'Owns',device:'Shared device/IP',p2p:'P2P purchase',
  deposit:'Deposit',withdrawal:'Withdrawal',crypto:'Wallet transfer',swap:'Swap',bridge:'Bridge',
  controls:'Controls',director:'Director of',alert:'Alert on',member:'Member of case',asset:'Holds asset'};
class FCGraph extends HTMLElement {
  connectedCallback(){
    ['data','highlightPath','filterEdges','filterTypes','minAmt','riskMin','timeT','perf','layout','selectId','communityOn','collapsed'].forEach(p=>{
      if(Object.prototype.hasOwnProperty.call(this,p)){ const v=this[p]; delete this[p]; this[p]=v; } });
    if(this._init) return; this._init=true;
    this.style.display='block'; this.style.overflow='hidden'; this.style.cursor='grab';
    if(getComputedStyle(this).position==='static') this.style.position='relative';
    this.cv=document.createElement('canvas'); this.cv.style.cssText='position:absolute;inset:0;width:100%;height:100%;display:block';
    this.tip=document.createElement('div');
    this.tip.style.cssText='position:absolute;pointer-events:none;background:rgba(10,23,36,0.97);border:1px solid rgba(133,173,209,0.3);border-radius:9px;padding:8px 11px;font:11px Geist,sans-serif;color:#E6F0F8;display:none;z-index:6;line-height:1.55;box-shadow:0 10px 30px rgba(0,0,0,0.5);max-width:280px';
    this.appendChild(this.cv); this.appendChild(this.tip);
    this.zoom=1; this.px=0; this.py=0; this.sel=null; this.selEdge=null; this.hov=null;
    this._hlPath=null; this._edgeF=null; this._typeF=null; this._minAmt=0; this._riskMin=0; this._timeT=1;
    this._perf=false; this._layoutMode='force'; this._commOn=false; this._collapsed={}; this._expanding=null;
    this._reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.ro=new ResizeObserver(()=>{ if(this._roQ) return; this._roQ=requestAnimationFrame(()=>{ this._roQ=null; this.resize(); this.draw(); }); });
    this.ro.observe(this); this.resize(); this._events();
    this._loop=()=>{ if(!this.isConnected){ this._raf=null; return; }
      if(this._anim>0){ this._anim-=1; this.draw(); }
      this._raf=requestAnimationFrame(this._loop); };
    this._raf=requestAnimationFrame(this._loop);
  }
  disconnectedCallback(){ if(this._raf){ cancelAnimationFrame(this._raf); this._raf=null; } }
  resize(){ const dpr=Math.min(devicePixelRatio||1,2); const w=this.clientWidth,h=this.clientHeight; if(!w||!h) return;
    this.cv.width=w*dpr; this.cv.height=h*dpr; this._dpr=dpr; }
  set data(v){ if(!v||!v.nodes) return;
    this.nodes=v.nodes.map(n=>({...n})); this.edges=v.edges.map(e=>({...e}));
    this.meta=v; this.byId={}; this.nodes.forEach(n=>this.byId[n.id]=n);
    this.layout(); this.fit(); }
  set layout_(v){}
  set highlightPath(ids){ this._hlPath=ids&&ids.length?ids:null; this.draw(); }
  set filterEdges(set){ this._edgeF=set; this.draw(); }
  set filterTypes(set){ this._typeF=set; this.draw(); }
  set minAmt(v){ this._minAmt=+v||0; this.draw(); }
  set riskMin(v){ this._riskMin=+v||0; this.draw(); }
  set timeT(v){ this._timeT=v==null?1:+v; this.draw(); }
  get perf(){ return this._perf; }
  set perf(v){ this._perf=!!v; this.draw(); }
  get timeT(){ return this._timeT; }
  get riskMin(){ return this._riskMin; }
  get minAmt(){ return this._minAmt; }
  get communityOn(){ return this._commOn; }
  set communityOn(v){ this._commOn=!!v; this.draw(); }
  set selectId(id){ const n=id&&this.byId?this.byId[id]:null; if(n===this.sel) return; this.sel=n||null; this.selEdge=null; this.draw(); }
  get layoutMode(){ return this._layoutMode; }
  set layoutMode(m){ if(this._layoutMode===m||!this.nodes) return; this._layoutMode=m; this.layout(true); this.fit(); }
  // ===== layouts =====
  layout(force){
    const N=this.nodes, E=this.edges; if(!N) return;
    if(this._layoutMode==='layered'||this._layoutMode==='dagre'){ this._layered(); return; }
    if(this._layoutMode==='circle'){ this._circle(); return; }
    if(this._layoutMode==='community'){ this._byCommunity(); return; }
    N.forEach((n,i)=>{ if(force||n.x==null){ const a=i/N.length*Math.PI*2; const R=250;
      n.x=Math.cos(a)*R*(0.45+((i*37)%53)/53*0.55); n.y=Math.sin(a)*R*(0.45+((i*29)%47)/47*0.55); n.fixed=false; } });
    for(let it=0;it<320;it++){ const k=it<200?1:0.35;
      for(let i=0;i<N.length;i++) for(let j=i+1;j<N.length;j++){
        const a=N[i],b=N[j]; let dx=a.x-b.x,dy=a.y-b.y; let d2=dx*dx+dy*dy||0.01; if(d2>160000) continue;
        const f=3400/d2*k; const d=Math.sqrt(d2); dx/=d; dy/=d;
        if(!a.fixed){a.x+=dx*f;a.y+=dy*f;} if(!b.fixed){b.x-=dx*f;b.y-=dy*f;} }
      E.forEach(e=>{ const a=this.byId[e.s],b=this.byId[e.t]; if(!a||!b) return;
        let dx=b.x-a.x,dy=b.y-a.y; const d=Math.hypot(dx,dy)||1; const f=(d-110)*0.014*k; dx/=d; dy/=d;
        if(!a.fixed){a.x+=dx*f;a.y+=dy*f;} if(!b.fixed){b.x-=dx*f;b.y-=dy*f;} });
      N.forEach(n=>{ if(!n.fixed){ n.x*=0.9985; n.y*=0.9985; } }); }
  }
  _stage(id){ // pipeline stage for layered layout
    const n=this.byId[id]; if(!n) return 0;
    const map={person:0,platform:1,account:2,org:2,device:1,wallet:4,contract:5,token:5,alert:6,case:6};
    if(/^pl/.test(id)) return 0; if(id==='plat') return 1; if(/^psp/.test(id)) return 2;
    if(/^m\d/.test(id)) return 3; if(/^p\d/.test(id)||/^d\d/.test(id)) return 3;
    if(/^agg/.test(id)||/^org/.test(id)||id==='mer1'||id==='pay1') return 4;
    if(/^v\d/.test(id)) return 5; if(/^vasp/.test(id)||/^va\d/.test(id)) return 6;
    if(/^w\d/.test(id)) return 7; if(id==='wop') return 8;
    if(/^sc|^ex|^tok/.test(id)) return 9; return 10;
  }
  _layered(){
    const cols={}; this.nodes.forEach(n=>{ const s=this._stage(n.id); (cols[s]=cols[s]||[]).push(n); });
    Object.keys(cols).forEach(s=>{ const list=cols[s]; const H=Math.max(1,list.length);
      list.forEach((n,i)=>{ n.x=(+s)*165-700; n.y=(i-(H-1)/2)*74; n.fixed=false; }); });
  }
  _circle(){ const N=this.nodes; N.forEach((n,i)=>{ const a=i/N.length*Math.PI*2;
    n.x=Math.cos(a)*300; n.y=Math.sin(a)*300; n.fixed=false; }); }
  _byCommunity(){
    const comms=[...new Set(this.nodes.map(n=>n.comm||'C0'))];
    comms.forEach((c,ci)=>{ const list=this.nodes.filter(n=>(n.comm||'C0')===c);
      const ang=ci/comms.length*Math.PI*2; const cx=Math.cos(ang)*330, cy=Math.sin(ang)*300;
      list.forEach((n,i)=>{ const a=i/Math.max(1,list.length)*Math.PI*2; const r=28+list.length*5.5;
        n.x=cx+Math.cos(a)*r; n.y=cy+Math.sin(a)*r; n.fixed=false; }); });
  }
  fit(){ const N=this.nodes; if(!N||!N.length) return; const w=this.clientWidth,h=this.clientHeight; if(!w) return;
    const vis=N.filter(n=>this._nodeVisible(n)); const use=vis.length?vis:N;
    const xs=use.map(n=>n.x), ys=use.map(n=>n.y);
    const minX=Math.min(...xs)-70,maxX=Math.max(...xs)+70,minY=Math.min(...ys)-60,maxY=Math.max(...ys)+60;
    this.zoom=Math.min(1.8,Math.min(w/(maxX-minX),h/(maxY-minY)));
    this.px=w/2-(minX+maxX)/2*this.zoom; this.py=h/2-(minY+maxY)/2*this.zoom; this.draw(); }
  focusNode(id){ const n=this.byId&&this.byId[id]; if(!n) return; this.sel=n; this.zoom=Math.max(1.1,this.zoom);
    this.px=this.clientWidth/2-n.x*this.zoom; this.py=this.clientHeight/2-n.y*this.zoom; this.draw(); }
  // ===== analysis =====
  neighbors(id,k){ const seen=new Set([id]); let frontier=[id];
    for(let i=0;i<(k||1);i++){ const next=[];
      this.edges.forEach(e=>{ if(frontier.includes(e.s)&&!seen.has(e.t)){ seen.add(e.t); next.push(e.t); }
        if(frontier.includes(e.t)&&!seen.has(e.s)){ seen.add(e.s); next.push(e.s); } });
      frontier=next; if(!next.length) break; }
    return [...seen]; }
  expandHop(id,k){ const ids=this.neighbors(id,k||1);
    this._expandSet=new Set(ids); this._expanding=id; this._anim=40;
    setTimeout(()=>{ this._expanding=null; this._anim=30; this.draw(); },420);
    this.draw(); return ids.length; }
  findPaths(src,dst,maxHop){
    const out=[]; const adj={}; this.edges.forEach(e=>{ (adj[e.s]=adj[e.s]||[]).push(e); });
    const walk=(cur,path,amt,edges)=>{ if(out.length>=8||path.length>(maxHop||7)) return;
      if(cur===dst){ out.push({nodes:[...path],edges:[...edges],amt}); return; }
      (adj[cur]||[]).forEach(e=>{ if(path.includes(e.t)) return;
        walk(e.t,[...path,e.t],Math.min(amt===0?e.amt||0:amt,e.amt||amt),[...edges,e]); }); };
    walk(src,[src],0,[]);
    return out.sort((a,b)=>(b.amt||0)-(a.amt||0));
  }
  // ===== visibility =====
  _nodeVisible(n){
    if(this._typeF&&this._typeF.size&&!this._typeF.has(n.type)) return false;
    if((n.risk||0)<this._riskMin) return false;
    if((n.t||0)>this._timeT) return false;
    return true; }
  _edgeVisible(e){
    if(this._edgeF&&this._edgeF.size&&!this._edgeF.has(e.kind)) return false;
    if(this._minAmt&&e.amt!=null&&e.amt<this._minAmt) return false;
    if((e.time||0)>this._timeT) return false;
    const a=this.byId[e.s],b=this.byId[e.t];
    if(!a||!b||!this._nodeVisible(a)||!this._nodeVisible(b)) return false;
    return true; }
  // ===== interaction =====
  _events(){
    const el=this.cv; let drag=null;
    el.addEventListener('pointerdown',e=>{ const n=this.nodeAt(e); el.setPointerCapture(e.pointerId); this._moved=false;
      drag=n?{node:n}:{pan:true,x:e.clientX,y:e.clientY,px:this.px,py:this.py}; this.style.cursor=n?'grabbing':'grabbing'; });
    el.addEventListener('pointermove',e=>{
      if(drag){ this._moved=true;
        if(drag.node){ const [wx,wy]=this.toWorld(e); drag.node.x=wx; drag.node.y=wy; drag.node.fixed=true; this.draw(); }
        else { this.px=drag.px+(e.clientX-drag.x); this.py=drag.py+(e.clientY-drag.y); this.draw(); } }
      else this._hover(e); });
    el.addEventListener('pointerup',e=>{ this.style.cursor='grab';
      if(!this._moved){ const pick=this.pickAt(e); const n=pick.node;
        if(n){ this.sel=n; this.selEdge=null; this.draw(); this.dispatchEvent(new CustomEvent('nodeselect',{detail:{...n}})); }
        else { const ed=pick.edge;
          if(ed){ this.selEdge=ed; this.sel=null; this.draw();
            this.dispatchEvent(new CustomEvent('edgeselect',{detail:{...ed, kindName:EDGE_LABEL[ed.kind]||ed.kind, sLabel:(this.byId[ed.s]||{}).label, tLabel:(this.byId[ed.t]||{}).label}})); }
          else { this.sel=null; this.selEdge=null; this._hlPath=null; this.draw(); this.dispatchEvent(new CustomEvent('nodeselect',{detail:null})); } } }
      drag=null; });
    el.addEventListener('dblclick',e=>{ const n=this.nodeAt(e); if(n){ this.expandHop(n.id,1);
      this.dispatchEvent(new CustomEvent('expand',{detail:{id:n.id,label:n.label}})); } });
    el.addEventListener('wheel',e=>{ e.preventDefault(); const f=e.deltaY<0?1.12:0.89;
      const r=el.getBoundingClientRect(); const mx=e.clientX-r.left,my=e.clientY-r.top;
      const nz=Math.min(4,Math.max(0.22,this.zoom*f)); const s=nz/this.zoom;
      this.px=mx-(mx-this.px)*s; this.py=my-(my-this.py)*s; this.zoom=nz; this.draw(); },{passive:false});
    el.addEventListener('mouseleave',()=>{ this.tip.style.display='none'; this.hov=null; this.draw(); });
  }
  toWorld(e){ const r=this.cv.getBoundingClientRect(); return [(e.clientX-r.left-this.px)/this.zoom,(e.clientY-r.top-this.py)/this.zoom]; }
  toScreen(n){ return [n.x*this.zoom+this.px, n.y*this.zoom+this.py]; }
  nodeAt(e,retDist){
    if(!this.nodes) return null;
    const r=this.cv.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
    let best=Infinity, hit=null;
    this.nodes.forEach(n=>{ if(!this._nodeVisible(n)) return;
      const p=this.toScreen(n); const lim=Math.max(9,(this._radius(n)+6)*this.zoom);
      const d=Math.hypot(p[0]-mx,p[1]-my); if(d<=lim&&d<best){ best=d; hit=n; } });
    return retDist?{node:hit,dist:best}:hit; }
  edgeDist(e){
    if(!this.edges) return {edge:null,dist:Infinity};
    const r=this.cv.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
    let best=Infinity, hit=null;
    this.edges.forEach(ed=>{ if(!this._edgeVisible(ed)) return;
      const a=this.byId[ed.s],b=this.byId[ed.t]; if(!a||!b) return;
      const p=this.toScreen(a),q=this.toScreen(b);
      for(let i=0;i<=20;i++){ const t=i/20; const x=p[0]+(q[0]-p[0])*t, y=p[1]+(q[1]-p[1])*t;
        const d=Math.hypot(x-mx,y-my); if(d<best){ best=d; hit=ed; } } });
    return {edge:best<=8?hit:null, dist:best}; }
  pickAt(e){
    const nh=this.nodeAt(e,true); const eh=this.edgeDist(e);
    if(nh.node&&eh.edge) return nh.dist<=eh.dist+1.5?{node:nh.node}:{edge:eh.edge};
    if(nh.node) return {node:nh.node};
    if(eh.edge) return {edge:eh.edge};
    return {}; }
  edgeAt(e){ if(!this.edges) return null; const r=this.cv.getBoundingClientRect();
    const mx=e.clientX-r.left,my=e.clientY-r.top; let best=7, hit=null;
    this.edges.forEach(ed=>{ if(!this._edgeVisible(ed)) return;
      const a=this.byId[ed.s],b=this.byId[ed.t]; const p=this.toScreen(a),q=this.toScreen(b);
      for(let i=0;i<=14;i++){ const t=i/14; const x=p[0]+(q[0]-p[0])*t, y=p[1]+(q[1]-p[1])*t;
        const d=Math.hypot(x-mx,y-my); if(d<best){ best=d; hit=ed; } } }); return hit; }
  _hover(e){
    const pick=this.pickAt(e); const n=pick.node||null; const ed=pick.edge||null;
    const changed=(n!==this.hov)||(ed!==this._hovE); this.hov=n; this._hovE=ed;
    if(changed) this.draw();
    const r=this.getBoundingClientRect(); const mx=e.clientX-r.left,my=e.clientY-r.top;
    this.style.cursor=(n||ed)?'pointer':'grab';
    if(n){ const st=TYPE[n.type]||TYPE.account;
      this.tip.innerHTML='<b>'+n.label+'</b> <span style="color:#607487">· '+st.name+'</span>'+
        (n.sub?'<br><span style="color:#91A4B5">'+n.sub+'</span>':'')+
        (n.risk!=null?'<br>Risk <b style="font-family:JetBrains Mono,monospace;color:'+this._rc(n.risk)+'">'+n.risk+'</b>':'')+
        (n.first?'<br><span style="color:#607487;font-size:10px">'+n.first+' → '+n.last+'</span>':'')+
        (n.negative?'<br><span style="color:#8FE8DF;font-size:10px">hard negative — hoạt động hợp pháp</span>':''); }
    else if(ed){ const a=this.byId[ed.s],b=this.byId[ed.t];
      this.tip.innerHTML='<b>'+(a||{}).label+' → '+(b||{}).label+'</b><br><span style="color:#91A4B5">'+(EDGE_LABEL[ed.kind]||ed.kind)+'</span>'+
        (ed.label?' · '+ed.label:'')+
        (ed.inferred?'<br><span style="color:#C9B8FC;font-size:10px">INFERRED · confidence '+(ed.conf!=null?ed.conf.toFixed(2):'—')+' — cần evidence xác nhận</span>':'')+
        (ed.sourceOnly?'<br><span style="color:#607487;font-size:10px">source-specific observation</span>':'')+
        (ed.ev?'<br><span style="font-family:JetBrains Mono,monospace;font-size:10px;color:#12D6C5">'+ed.ev+'</span>':''); }
    if(n||ed){ this.tip.style.display='block'; const tw=this.tip.offsetWidth;
      let lx=mx+15; if(lx+tw>r.width-4) lx=mx-tw-15;
      this.tip.style.left=lx+'px'; this.tip.style.top=Math.max(4,Math.min(r.height-60,my-16))+'px'; }
    else this.tip.style.display='none';
  }
  _rc(r){ return r>=80?'#FF4D61':r>=55?'#F5A524':'#2DD4A7'; }
  // ===== shapes =====
  _shape(g,n,r,st){
    const x=n.x,y=n.y;
    g.beginPath();
    switch(st.shape){
      case 'rect': g.rect(x-r*1.15,y-r*0.78,r*2.3,r*1.56); break;
      case 'rrect': { const w=r*2.2,h=r*1.5,rad=r*0.35; this._rr(g,x-w/2,y-h/2,w,h,rad); break; }
      case 'rrect-lg': { const w=r*2.6,h=r*1.8,rad=r*0.4; this._rr(g,x-w/2,y-h/2,w,h,rad); break; }
      case 'pill': { const w=r*2.3,h=r*1.35; this._rr(g,x-w/2,y-h/2,w,h,h/2); break; }
      case 'diamond': case 'diamond2':
        g.moveTo(x,y-r*1.25); g.lineTo(x+r*1.15,y); g.lineTo(x,y+r*1.25); g.lineTo(x-r*1.15,y); g.closePath(); break;
      case 'hex': for(let i=0;i<6;i++){ const a=Math.PI/6+i*Math.PI/3; const px=x+Math.cos(a)*r*1.15,py=y+Math.sin(a)*r*1.15; i?g.lineTo(px,py):g.moveTo(px,py); } g.closePath(); break;
      case 'octagon': for(let i=0;i<8;i++){ const a=Math.PI/8+i*Math.PI/4; const px=x+Math.cos(a)*r*1.2,py=y+Math.sin(a)*r*1.2; i?g.lineTo(px,py):g.moveTo(px,py); } g.closePath(); break;
      case 'warning': g.moveTo(x,y-r*1.2); g.lineTo(x+r*1.15,y+r*0.85); g.lineTo(x-r*1.15,y+r*0.85); g.closePath(); break;
      case 'container': { const w=r*2.7,h=r*1.7; this._rr(g,x-w/2,y-h/2,w,h,r*0.28); break; }
      default: g.arc(x,y,r,0,7);
    }
  }
  _rr(g,x,y,w,h,r){ g.moveTo(x+r,y); g.lineTo(x+w-r,y); g.quadraticCurveTo(x+w,y,x+w,y+r);
    g.lineTo(x+w,y+h-r); g.quadraticCurveTo(x+w,y+h,x+w-r,y+h); g.lineTo(x+r,y+h);
    g.quadraticCurveTo(x,y+h,x,y+h-r); g.lineTo(x,y+r); g.quadraticCurveTo(x,y,x+r,y); g.closePath(); }
  draw(){
    if(!this.nodes||!this._dpr) return;
    const g=this.cv.getContext('2d'); const w=this.clientWidth,h=this.clientHeight;
    g.setTransform(this._dpr,0,0,this._dpr,0,0); g.clearRect(0,0,w,h);
    g.save(); g.translate(this.px,this.py); g.scale(this.zoom,this.zoom);
    const selId=this.sel&&this.sel.id;
    const nbr=new Set(); if(selId) this.edges.forEach(e=>{ if(e.s===selId)nbr.add(e.t); if(e.t===selId)nbr.add(e.s); });
    const path=this._hlPath; const inPath=id=>path&&path.includes(id);
    const expSet=this._expandSet;
    // community hulls
    if(this._commOn&&this.meta&&this.meta.communities){
      this.meta.communities.forEach(c=>{
        const list=this.nodes.filter(n=>(n.comm)===c.id&&this._nodeVisible(n)); if(list.length<2) return;
        const xs=list.map(n=>n.x),ys=list.map(n=>n.y);
        const x0=Math.min(...xs)-34,x1=Math.max(...xs)+34,y0=Math.min(...ys)-30,y1=Math.max(...ys)+30;
        g.beginPath(); this._rr(g,x0,y0,x1-x0,y1-y0,22);
        g.fillStyle=c.color+'12'; g.fill(); g.strokeStyle=c.color+'55'; g.lineWidth=1.2; g.setLineDash([6,5]); g.stroke(); g.setLineDash([]);
        g.fillStyle=c.color; g.font='600 11px Geist,sans-serif'; g.textAlign='left';
        g.fillText(c.name+' ('+list.length+')', x0+8, y0-7);
      });
    }
    // edges
    this.edges.forEach(e=>{ if(!this._edgeVisible(e)) return;
      const a=this.byId[e.s],b=this.byId[e.t];
      const onPath=path&&inPath(e.s)&&inPath(e.t)&&Math.abs(path.indexOf(e.s)-path.indexOf(e.t))===1;
      const touched=selId&&(e.s===selId||e.t===selId);
      const isSelE=this.selEdge===e; const hovE=this._hovE===e;
      let alpha=(selId||path)?((touched||onPath)?0.95:0.08):(e.sourceOnly?0.3:0.5);
      if(isSelE||hovE) alpha=1;
      if(expSet&&!expSet.has(e.s)&&!expSet.has(e.t)) alpha*=0.35;
      const col=onPath?'#FF4D61':isSelE?'#12D6C5':(e.inferred?'#A78BFA':e.sourceOnly?'#607487':'#8FAAC4');
      const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,ux=dx/d,uy=dy/d;
      const ra=this._radius(a)+5, rb=this._radius(b)+9;
      const x1=a.x+ux*ra,y1=a.y+uy*ra,x2=b.x-ux*rb,y2=b.y-uy*rb;
      let lw=e.w||1;
      if(e.amt!=null) lw=Math.max(0.8,Math.min(4.2,Math.log10(1+e.amt)*0.62));
      if(onPath) lw=Math.max(lw,2.6); if(isSelE) lw=Math.max(lw,2.4);
      g.beginPath(); g.moveTo(x1,y1); g.lineTo(x2,y2);
      g.strokeStyle=col; g.globalAlpha=alpha; g.lineWidth=lw;
      g.setLineDash(e.inferred?[5,4]:e.sourceOnly?[2,4]:[]); g.stroke(); g.setLineDash([]);
      const money=e.amt!=null&&e.kind!=='owns';
      if(money||e.kind==='transfer'||e.kind==='crypto'){
        g.beginPath(); g.moveTo(x2,y2); g.lineTo(x2-ux*8-uy*3.8,y2-uy*8+ux*3.8); g.lineTo(x2-ux*8+uy*3.8,y2-uy*8-ux*3.8);
        g.closePath(); g.fillStyle=col; g.fill(); }
      const showLbl=!this._perf&&e.label&&(isSelE||hovE||touched||onPath||this.zoom>1.35);
      if(showLbl){ g.globalAlpha=1; g.font='9px Geist,sans-serif'; g.textAlign='center';
        const mx=(x1+x2)/2,my=(y1+y2)/2; const tw=g.measureText(e.label).width;
        g.fillStyle='rgba(5,11,18,0.86)'; g.fillRect(mx-tw/2-4,my-13,tw+8,13);
        g.fillStyle=e.inferred?'#C9B8FC':onPath?'#FF9BA6':'#A9BECE'; g.fillText(e.label,mx,my-6); }
      g.globalAlpha=1; });
    // nodes
    this.nodes.forEach(n=>{ if(!this._nodeVisible(n)) return;
      const st=TYPE[n.type]||TYPE.account; const r=this._radius(n);
      const isSel=selId===n.id, isNbr=nbr.has(n.id), onPath=inPath(n.id), isHov=this.hov===n;
      let alpha=(selId||path)?((isSel||isNbr||onPath)?1:0.2):1;
      if(expSet&&!expSet.has(n.id)) alpha*=0.4;
      g.globalAlpha=alpha;
      // risk ring (thickness + ring, not colour only)
      if((n.risk||0)>=80){ g.beginPath(); g.arc(n.x,n.y,r+7,0,7); g.strokeStyle='rgba(255,77,97,0.55)'; g.lineWidth=1.3; g.setLineDash([3,3]); g.stroke(); g.setLineDash([]); }
      else if((n.risk||0)>=55){ g.beginPath(); g.arc(n.x,n.y,r+6,0,7); g.strokeStyle='rgba(245,165,36,0.4)'; g.lineWidth=1; g.setLineDash([2,4]); g.stroke(); g.setLineDash([]); }
      if(this._expanding&&expSet&&expSet.has(n.id)&&n.id!==this._expanding&&!this._reduced){
        g.beginPath(); g.arc(n.x,n.y,r+10+((Date.now()/12)%14),0,7); g.strokeStyle='rgba(18,214,197,0.35)'; g.lineWidth=1; g.stroke(); }
      this._shape(g,n,r,st);
      g.fillStyle=n.negative?'#0B1A16':'#0D1C2A'; g.fill();
      g.strokeStyle=st.c; g.lineWidth=isSel?2.8:(n.risk||0)>=80?2.4:(n.risk||0)>=55?1.8:1.2;
      if(isSel){ g.save(); g.shadowColor=st.c; g.shadowBlur=14; g.stroke(); g.restore(); } else g.stroke();
      if(st.shape==='diamond2'){ this._shape(g,{...n},r*0.72,st); g.lineWidth=1; g.strokeStyle=st.c+'99'; g.stroke(); }
      if(n.canonical===false){ g.beginPath(); g.arc(n.x,n.y,r-3.5,0,7); g.strokeStyle=st.c+'55'; g.lineWidth=1; g.setLineDash([2,3]); g.stroke(); g.setLineDash([]); }
      g.fillStyle=st.c; g.font='600 '+Math.round(r*0.76)+'px "JetBrains Mono",monospace';
      g.textAlign='center'; g.textBaseline='middle'; g.fillText(st.g,n.x,n.y+0.5);
      // severity badge
      if((n.risk||0)>=55){ const bx=n.x+r*0.95, by=n.y-r*0.95;
        g.beginPath(); g.arc(bx,by,6.4,0,7); g.fillStyle=(n.risk>=80?'#FF4D61':'#F5A524'); g.fill();
        g.fillStyle='#050B12'; g.font='700 8px "JetBrains Mono",monospace'; g.fillText(n.risk>=80?'!':'▲',bx,by+0.4); }
      if(n.negative){ const bx=n.x-r*0.95, by=n.y-r*0.95;
        g.beginPath(); g.arc(bx,by,6,0,7); g.fillStyle='#2DD4A7'; g.fill();
        g.fillStyle='#050B12'; g.font='700 8px "JetBrains Mono",monospace'; g.fillText('✓',bx,by+0.4); }
      if(!this._perf&&(this.zoom>0.45||isSel||isHov)){
        g.font='500 10px Geist,sans-serif'; g.fillStyle='rgba(230,240,248,'+(0.9*alpha)+')';
        g.fillText(n.label,n.x,n.y+r+12);
        if(n.sub&&(this.zoom>0.8||isSel||isHov)){ g.font='8.5px "JetBrains Mono",monospace';
          g.fillStyle='rgba(96,116,135,'+alpha+')'; g.fillText(n.sub,n.x,n.y+r+23); } }
      g.globalAlpha=1; g.textBaseline='middle'; });
    g.restore();
    // minimap
    if(!this._perf) this._minimap(g,w,h);
  }
  _radius(n){ return n.r||16; }
  _minimap(g,w,h){
    const mw=110,mh=76,mx=w-mw-10,my=h-mh-10;
    const vis=this.nodes.filter(n=>this._nodeVisible(n)); if(!vis.length) return;
    const xs=vis.map(n=>n.x),ys=vis.map(n=>n.y);
    const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
    const sx=(x1-x0)||1, sy=(y1-y0)||1; const k=Math.min((mw-12)/sx,(mh-12)/sy);
    g.fillStyle='rgba(7,17,28,0.86)'; g.strokeStyle='rgba(133,173,209,0.18)'; g.lineWidth=1;
    g.beginPath(); this._rr(g,mx,my,mw,mh,8); g.fill(); g.stroke();
    vis.forEach(n=>{ const px=mx+6+(n.x-x0)*k, py=my+6+(n.y-y0)*k;
      g.fillStyle=(n.risk||0)>=80?'#FF4D61':(n.risk||0)>=55?'#F5A524':'#3A6E8A';
      g.fillRect(px-1,py-1,2.2,2.2); });
    // viewport rect
    const vx0=(-this.px)/this.zoom, vy0=(-this.py)/this.zoom;
    const vx1=vx0+this.clientWidth/this.zoom, vy1=vy0+this.clientHeight/this.zoom;
    const rx=mx+6+(vx0-x0)*k, ry=my+6+(vy0-y0)*k, rw=(vx1-vx0)*k, rh=(vy1-vy0)*k;
    g.strokeStyle='rgba(18,214,197,0.6)'; g.lineWidth=1;
    g.strokeRect(Math.max(mx+2,rx),Math.max(my+2,ry),Math.min(mw-4,rw),Math.min(mh-4,rh));
  }
}
customElements.define('fc-graph', FCGraph);
})();
