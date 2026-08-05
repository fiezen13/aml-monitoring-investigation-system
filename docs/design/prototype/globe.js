/* fc-globe: interactive 3D financial-flow globe (canvas, orthographic 3D projection) */
(() => {
// 5° landmask built from per-latitude longitude ranges (row r → lat center 87.5-5r)
const LAND_RANGES = [
  [], [[-60,-20],[80,105]], [[-120,-18],[50,115]], [[-130,-18],[8,180]],
  [[-168,-58],[-56,-20],[4,180]], [[-168,-54],[-52,-38],[-2,180]], [[-168,-54],[-11,180]],
  [[-172,-154],[-132,-54],[-11,180]], [[-126,-56],[-6,180]], [[-125,-68],[-10,146]],
  [[-123,-74],[-10,142]], [[-121,-77],[-11,136]], [[-116,-80],[-14,123]],
  [[-111,-96],[-86,-74],[-17,119]], [[-106,-87],[-17,110]], [[-93,-82],[-17,108],[119,127]],
  [[-81,-71],[-14,48],[94,108],[119,127]], [[-79,-49],[-11,46],[95,119]],
  [[-81,-34],[7,43],[99,136],[131,151]], [[-79,-34],[10,41],[104,120],[130,151]],
  [[-76,-34],[11,41],[104,131]], [[-73,-37],[11,38],[42,51],[117,148]],
  [[-71,-39],[13,36],[42,49],[112,153]], [[-72,-47],[14,34],[112,154]],
  [[-73,-52],[16,31],[114,153]], [[-74,-56],[134,151],[171,179]],
  [[-75,-62],[169,177]], [[-76,-67]], [[-75,-68]], [],
  [[-66,-57]], [[-102,-54],[8,162]], [[-180,180]], [[-180,180]], [[-180,180]], [[-180,180]],
];
const MASK = LAND_RANGES.map(rs=>{ const row=new Array(72).fill('0');
  rs.forEach(([a,b])=>{ for(let c=0;c<72;c++){ const lon=-180+c*5+2.5; if(lon>=a&&lon<=b) row[c]='1'; } });
  return row.join(''); });
const CH_COLOR = {bank:'#3185FF', p2p:'#12D6C5', vasp:'#A78BFA', chain:'#2DD4A7', gamb:'#F5A524', proj:'#FF8A5C'};
const RISK_COLOR = {ok:null, warn:'#F5A524', crit:'#FF4D61'};
function ll2v(lat,lon){ const la=lat*Math.PI/180, lo=lon*Math.PI/180; return [Math.cos(la)*Math.sin(lo), Math.sin(la), Math.cos(la)*Math.cos(lo)]; }
function slerp(a,b,t){ let d=a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; d=Math.min(1,Math.max(-1,d)); const th=Math.acos(d); if(th<1e-4) return a;
  const s=Math.sin(th), w1=Math.sin((1-t)*th)/s, w2=Math.sin(t*th)/s;
  return [a[0]*w1+b[0]*w2, a[1]*w1+b[1]*w2, a[2]*w1+b[2]*w2]; }
class FCGlobe extends HTMLElement {
  connectedCallback(){
    if(this._init){ this.startLoop(); return; } this._init=true;
    this.style.display='block'; this.style.overflow='hidden'; this.style.cursor='grab';
    if(getComputedStyle(this).position==='static') this.style.position='relative';
    this.cv=document.createElement('canvas'); this.cv.style.cssText='width:100%;height:100%;display:block';
    this.tip=document.createElement('div');
    this.tip.style.cssText='position:absolute;pointer-events:none;background:rgba(10,23,36,0.96);border:1px solid rgba(133,173,209,0.28);border-radius:10px;padding:9px 12px;font:11px Geist,sans-serif;color:#E6F0F8;display:none;z-index:6;line-height:1.55;box-shadow:0 10px 30px rgba(0,0,0,0.5);min-width:170px';
    this.appendChild(this.cv); this.appendChild(this.tip);
    this.rot=-1.2; this.tilt=0.42; this.autoSpin=true; this.speed=1; this.layers=null; this.paused=false;
    this.hubs=[]; this.flows=[]; this.t=0; this.hover=null; this.selected=null;
    this.ro=new ResizeObserver(()=>{ if(this._roQ) return; this._roQ=requestAnimationFrame(()=>{ this._roQ=null; this.resize(); }); }); this.ro.observe(this); this.resize();
    let drag=null;
    this.cv.addEventListener('pointerdown',e=>{ drag={x:e.clientX,y:e.clientY,rot:this.rot,tilt:this.tilt}; this.autoSpin=false; this.style.cursor='grabbing'; this.cv.setPointerCapture(e.pointerId); this._moved=false; });
    this.cv.addEventListener('pointermove',e=>{
      if(drag){ this.rot=drag.rot+(e.clientX-drag.x)*0.006; this.tilt=Math.min(1.1,Math.max(-0.4,drag.tilt+(e.clientY-drag.y)*0.004)); if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>4)this._moved=true; }
      else this.pick(e);
    });
    this.cv.addEventListener('pointerup',e=>{ drag=null; this.style.cursor='grab';
      if(!this._moved){ this.pick(e); if(this.hover&&this.hover.kind==='hub'){ this.selected=this.hover.hub; this.dispatchEvent(new CustomEvent('hubselect',{detail:this.hover.hub})); } } });
    this.cv.addEventListener('mouseleave',()=>{ this.hover=null; this.tip.style.display='none'; });
    this.startLoop();
  }
  set data(v){ if(!v) return; this.hubs=v.hubs||[]; this.flows=v.flows||[]; }
  startLoop(){
    if(this._raf) return;
    const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    const loop=()=>{ if(!this.isConnected){ this._raf=null; return; }
      if(!this.paused) this.t+=(reduced?0:0.004*this.speed); if(this.autoSpin&&!reduced) this.rot+=0.0009; this.draw(); this._raf=requestAnimationFrame(loop); };
    this._raf=requestAnimationFrame(loop);
  }
  resize(){ const dpr=window.devicePixelRatio||1; this.cv.width=this.clientWidth*dpr; this.cv.height=this.clientHeight*dpr; this._dpr=dpr; }
  proj(v){ // rotate by rot around Y then tilt around X
    const cr=Math.cos(this.rot), sr=Math.sin(this.rot);
    let x=v[0]*cr - v[2]*sr, z=v[0]*sr + v[2]*cr, y=v[1];
    const ct=Math.cos(this.tilt), st=Math.sin(this.tilt);
    const y2=y*ct - z*st, z2=y*st + z*ct;
    return [this.cx + x*this.R, this.cy - y2*this.R, z2];
  }
  flowVisible(f){ return !this.layers || this.layers[f.ch]!==false; }
  pick(e){
    const r=this.cv.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
    let best=14, hit=null;
    this.hubs.forEach(hb=>{ const p=this.proj(ll2v(hb.lat,hb.lon)); if(p[2]<=0) return;
      const d=Math.hypot(p[0]-mx,p[1]-my); if(d<best){ best=d; hit={kind:'hub',hub:hb,x:p[0],y:p[1]}; } });
    if(!hit){ let bd=8;
      this.flows.forEach(f=>{ if(!this.flowVisible(f)) return; const pts=this.arcPts(f,14);
        for(const p of pts){ if(p[2]<=0) continue; const d=Math.hypot(p[0]-mx,p[1]-my); if(d<bd){ bd=d; hit={kind:'flow',flow:f,x:mx,y:my}; } } }); }
    this.hover=hit;
    if(hit){ const T=this.tip;
      if(hit.kind==='hub'){ const hb=hit.hub;
        T.innerHTML='<b style="font-size:12px">'+hb.name+'</b><br><span style="color:#91A4B5">Entities:</span> <b style="font-family:JetBrains Mono,monospace">'+hb.entities.toLocaleString('vi-VN')+'</b><br><span style="color:#91A4B5">Alerts mở:</span> <b style="font-family:JetBrains Mono,monospace;color:'+(hb.alerts>20?'#FF4D61':'#E6F0F8')+'">'+hb.alerts+'</b><br><span style="color:#607487;font-size:10px">Click để mở panel khu vực</span>'; }
      else { const f=hit.flow; const chName={bank:'Bank transfer',p2p:'P2P conversion',vasp:'VASP flow',chain:'Cross-chain bridge',gamb:'Gambling settlement',proj:'Project/token flow'}[f.ch];
        T.innerHTML='<b style="font-size:12px">'+f.sn+' → '+f.tn+'</b><br><span style="color:#91A4B5">Kênh:</span> '+chName+'<br><span style="color:#91A4B5">Volume 24h:</span> <b style="font-family:JetBrains Mono,monospace">$'+f.vol+'</b> · '+f.txn+' txn<br><span style="color:#91A4B5">Risk:</span> <b style="color:'+(f.risk==='crit'?'#FF4D61':f.risk==='warn'?'#F5A524':'#2DD4A7')+'">'+(f.risk==='crit'?'CRITICAL':f.risk==='warn'?'ELEVATED':'NORMAL')+'</b>'+(f.typ?'<br><span style="color:#91A4B5">Typology:</span> '+f.typ:''); }
      T.style.display='block'; const tw=T.offsetWidth; let lx=hit.x+16; if(lx+tw>r.width-4) lx=hit.x-tw-16;
      T.style.left=lx+'px'; T.style.top=Math.max(4,hit.y-20)+'px';
    } else this.tip.style.display='none';
  }
  arcPts(f,n){
    if(!f._va){ f._va=ll2v(f.slat,f.slon); f._vb=ll2v(f.tlat,f.tlon);
      const d=Math.acos(Math.min(1,f._va[0]*f._vb[0]+f._va[1]*f._vb[1]+f._va[2]*f._vb[2])); f._alt=0.06+d*0.13; }
    const pts=[];
    for(let i=0;i<=n;i++){ const t=i/n; const v=slerp(f._va,f._vb,t); const alt=1+f._alt*Math.sin(t*Math.PI);
      const p=this.proj([v[0]*alt,v[1]*alt,v[2]*alt]); pts.push(p); }
    return pts;
  }
  draw(){
    if(!this._styleFixed){ this._styleFixed=1; this.style.display='block'; if(getComputedStyle(this).position==='static') this.style.position='relative'; }
    const g=this.cv.getContext('2d'); const dpr=this._dpr||1; const w=this.clientWidth, h=this.clientHeight; if(!w) return;
    g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,w,h);
    this.cx=w/2; this.cy=h/2+6; this.R=Math.min(w,h)/2-Math.min(w,h)*0.09;
    const {cx,cy,R}=this;
    // atmosphere + sphere
    let gr=g.createRadialGradient(cx,cy,R*0.7,cx,cy,R*1.28); gr.addColorStop(0,'rgba(18,90,120,0)'); gr.addColorStop(0.78,'rgba(18,150,170,0.10)'); gr.addColorStop(1,'rgba(18,150,170,0)');
    g.fillStyle=gr; g.beginPath(); g.arc(cx,cy,R*1.28,0,7); g.fill();
    gr=g.createRadialGradient(cx-R*0.35,cy-R*0.4,R*0.1,cx,cy,R); gr.addColorStop(0,'#102438'); gr.addColorStop(0.65,'#0A1928'); gr.addColorStop(1,'#071220');
    g.fillStyle=gr; g.beginPath(); g.arc(cx,cy,R,0,7); g.fill();
    g.strokeStyle='rgba(133,173,209,0.20)'; g.lineWidth=1; g.stroke();
    // graticule
    g.strokeStyle='rgba(133,173,209,0.07)';
    for(let lat=-60;lat<=60;lat+=30){ g.beginPath(); let started=false;
      for(let lon=-180;lon<=180;lon+=6){ const p=this.proj(ll2v(lat,lon)); if(p[2]>0){ if(started) g.lineTo(p[0],p[1]); else {g.moveTo(p[0],p[1]); started=true;} } else started=false; } g.stroke(); }
    for(let lon=-180;lon<180;lon+=30){ g.beginPath(); let started=false;
      for(let lat=-85;lat<=85;lat+=5){ const p=this.proj(ll2v(lat,lon)); if(p[2]>0){ if(started) g.lineTo(p[0],p[1]); else {g.moveTo(p[0],p[1]); started=true;} } else started=false; } g.stroke(); }
    // land dots
    for(let r2=0;r2<36;r2++){ const row=MASK[r2]; const lat=85-r2*(170/35);
      for(let c=0;c<72;c++){ if(row[c]!=='1') continue; const lon=-180+c*5+2.5;
        const p=this.proj(ll2v(lat,lon)); if(p[2]<=0.02) continue;
        g.fillStyle='rgba(120,170,210,'+(0.30+p[2]*0.35)+')';
        g.beginPath(); g.arc(p[0],p[1],Math.max(1.1,R*0.013*(0.6+p[2]*0.5)),0,7); g.fill(); } }
    // flows
    this.flows.forEach(f=>{ if(!this.flowVisible(f)) return;
      const pts=this.arcPts(f,36); const col=f.risk==='crit'?'#FF4D61':f.risk==='warn'?'#F5A524':CH_COLOR[f.ch]||'#3185FF';
      const susp=f.risk==='crit'||f.risk==='warn';
      g.beginPath(); let started=false;
      pts.forEach(p=>{ if(p[2]>-0.05){ if(started) g.lineTo(p[0],p[1]); else {g.moveTo(p[0],p[1]); started=true;} } else started=false; });
      g.strokeStyle=col+(susp?'66':'2E'); g.lineWidth=susp?1.4:0.8;
      if(susp){ g.save(); g.shadowColor=col; g.shadowBlur=4; g.stroke(); g.restore(); } else g.stroke();
      // moving pulse
      const n=pts.length-1; const ph=((this.t*(susp?1.6:0.7)+(f.ph||0))%1);
      const i=Math.floor(ph*n); const p=pts[i];
      if(p&&p[2]>0){ g.beginPath(); g.arc(p[0],p[1],susp?2.6:1.4,0,7); g.fillStyle=col; g.save(); if(susp){g.shadowColor=col; g.shadowBlur=8;} g.fill(); g.restore(); }
    });
    // hubs
    this.hubs.forEach(hb=>{ const p=this.proj(ll2v(hb.lat,hb.lon)); if(p[2]<=0) return;
      const base=Math.max(2,R*0.012+hb.size*R*0.006);
      const col=hb.alerts>20?'#FF4D61':hb.alerts>8?'#F5A524':'#12D6C5';
      const isSel=this.selected&&this.selected.id===hb.id;
      const isHov=this.hover&&this.hover.kind==='hub'&&this.hover.hub.id===hb.id;
      if(hb.alerts>8){ const pr=base+((this.t*3+hb.size)%1)*base*2.4;
        g.beginPath(); g.arc(p[0],p[1],pr,0,7); g.strokeStyle=col+'55'; g.lineWidth=1; g.stroke(); }
      g.beginPath(); g.arc(p[0],p[1],base+(isHov?1.5:0),0,7); g.fillStyle=col;
      g.save(); if(isSel||isHov){ g.shadowColor=col; g.shadowBlur=10; } g.fill(); g.restore();
      g.beginPath(); g.arc(p[0],p[1],base+3,0,7); g.strokeStyle=isSel?col:'rgba(230,240,248,0.35)'; g.lineWidth=isSel?1.5:0.5; g.stroke();
      if(p[2]>0.35||isSel){ g.font='600 10px Geist,sans-serif'; g.textAlign='left'; g.fillStyle='rgba(230,240,248,'+(0.5+p[2]*0.5)+')'; g.fillText(hb.name, p[0]+base+6, p[1]-2);
        g.font='9px "JetBrains Mono",monospace'; g.fillStyle='rgba(145,164,181,'+(0.4+p[2]*0.5)+')'; g.fillText('$'+hb.vol, p[0]+base+6, p[1]+9); }
    });
  }
}
if(!customElements.get('fc-globe')) customElements.define('fc-globe', FCGlobe);
})();
