/* fc-worldmap: flat dark intelligence world map (canvas) — countries, financial hubs, corridor flows */
// Ranh giới quốc gia đi kèm bundle. Trước đây tải từ jsdelivr lúc chạy —
// một console tuân thủ ngân hàng thường nằm sau mạng chặn Internet ra ngoài,
// và khi CDN không tới được thì bản đồ mất luôn đường biên.
import TOPO from 'world-atlas/countries-110m.json';
(() => {
if (customElements.get('fc-worldmap')) return;
const CH = {
  bank:{c:'#3185FF',n:'BANK_TRANSFER'}, p2p:{c:'#12D6C5',n:'P2P_SETTLEMENT'}, vasp:{c:'#A78BFA',n:'VASP_FLOW'},
  chain:{c:'#2DD4A7',n:'CRYPTO_BRIDGE'}, gamb:{c:'#F5A524',n:'GAMBLING_SETTLEMENT'}, proj:{c:'#FF8A5C',n:'TOKEN_FLOW'}
};
const LAT_TOP = 82, LAT_BOT = -58;
// label placement per hub id: [dx, dy, align]
const LBL = {
  hn:[-8,-16,'right'], sgn:[-8,16,'right'], pp:[10,-14,'left'], bkk:[-10,-6,'right'], sg:[9,15,'left'],
  hk:[10,-13,'left'], sel:[9,-13,'left'], tk:[10,4,'left'], du:[9,12,'left'], fra:[8,13,'left'],
  ldn:[-8,-13,'right'], ny:[-9,4,'right'], sf:[-9,-11,'right'], sp:[-9,12,'right'], lag:[-9,12,'right'], syd:[9,10,'left'], mnl:[10,10,'left']
};
const ALWAYS = new Set(['sgn','sg','hk','ldn','ny','tk','du','fra','sf','syd','sp','lag']);
function decode(topo){
  const [sx,sy]=topo.transform.scale, [tx,ty]=topo.transform.translate;
  const arcs=topo.arcs.map(a=>{ let x=0,y=0; return a.map(d=>{ x+=d[0]; y+=d[1]; return [x*sx+tx, y*sy+ty]; }); });
  const ring=is=>{ const out=[]; is.forEach(i=>{ const p=i<0?arcs[~i].slice().reverse():arcs[i]; out.push(...(out.length?p.slice(1):p)); }); return out; };
  const polys=[];
  (topo.objects.countries.geometries||[]).forEach(gm=>{
    if(gm.type==='Polygon') polys.push(gm.arcs.map(ring));
    else if(gm.type==='MultiPolygon') gm.arcs.forEach(p=>polys.push(p.map(ring)));
  });
  return polys;
}
class FCWorldMap extends HTMLElement {
  connectedCallback(){
    ['data','layers','sev','typ','topN','hideNormal','speed','paused','replay','selection','hubSelection'].forEach(p=>{
      if(Object.prototype.hasOwnProperty.call(this,p)){ const v=this[p]; delete this[p]; this[p]=v; } });
    if(this._init){ this._start(); return; }
    this._init=true;
    this.style.display='block'; this.style.overflow='hidden'; this.style.cursor='grab';
    if(getComputedStyle(this).position==='static') this.style.position='relative';
    this.cv=document.createElement('canvas'); this.cv.style.cssText='position:absolute;inset:0;width:100%;height:100%;display:block';
    this.tip=document.createElement('div');
    this.tip.style.cssText='position:absolute;pointer-events:none;background:rgba(10,23,36,0.97);border:1px solid rgba(133,173,209,0.3);border-radius:10px;padding:9px 12px;font:11px Geist,sans-serif;color:#E6F0F8;display:none;z-index:6;line-height:1.55;box-shadow:0 12px 34px rgba(0,0,0,0.55);min-width:190px';
    this.state=document.createElement('div');
    this.state.style.cssText='position:absolute;inset:0;display:grid;place-items:center;color:#607487;font:12px Geist,sans-serif;z-index:3;text-align:center;padding:20px';
    this.state.innerHTML='<div><div style="width:30px;height:30px;margin:0 auto 10px;border-radius:50%;border:2px solid rgba(18,214,197,0.15);border-top-color:#12D6C5;animation:fcSpin .9s linear infinite"></div>Đang tải bản đồ thế giới…</div><style>@keyframes fcSpin{to{transform:rotate(360deg)}}</style>';
    this.appendChild(this.cv); this.appendChild(this.tip); this.appendChild(this.state);
    this.k=1; this.ox=0; this.oy=0; this.t=0; this._paused=false; this._speed=1;
    this._layers=null; this._sev='all'; this._typ='all'; this._topN=0; this._hideNormal=false;
    this._replay={on:false,t:1}; this._sel=null; this._selHub=null; this._hov=null; this._shocks=[];
    this._reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.ro=new ResizeObserver(()=>{ if(this._roQ) return; this._roQ=requestAnimationFrame(()=>{ this._roQ=null; this._resize(); }); });
    this.ro.observe(this); this._resize(); this._events();
    document.addEventListener('visibilitychange',()=>{ this._hidden=document.hidden; });
    try{ this.polys=decode(TOPO); this.state.remove(); }
    catch(e){ this.state.innerHTML='<div style="max-width:280px;line-height:1.6"><div style="color:#F5A524;margin-bottom:6px">Không đọc được ranh giới quốc gia</div><span style="font-size:11px">Bản đồ chạy ở chế độ tối giản — corridor và hub vẫn hoạt động bình thường.</span></div>';
      setTimeout(()=>this.state.remove(),2600); this.polys=[]; }
    this._start();
  }
  disconnectedCallback(){ if(this._raf){ cancelAnimationFrame(this._raf); this._raf=null; } }
  _start(){ if(this._raf) return;
    const loop=()=>{ if(!this.isConnected){ this._raf=null; return; }
      if(!this._hidden){ if(!this._paused&&!this._reduced) this.t+=0.016*this._speed; this.draw(); }
      this._raf=requestAnimationFrame(loop); };
    this._raf=requestAnimationFrame(loop); }
  set data(v){ if(!v) return; this._data=v; this._prep(); }
  set layers(v){ this._layers=v; this._prep(); }
  set sev(v){ if(this._sev===v) return; this._sev=v; this._prep(); }
  set typ(v){ if(this._typ===v) return; this._typ=v; this._prep(); }
  set topN(v){ if(this._topN===+v) return; this._topN=+v; this._prep(); }
  set hideNormal(v){ if(this._hideNormal===!!v) return; this._hideNormal=!!v; this._prep(); }
  set speed(v){ this._speed=v; }
  set paused(v){ this._paused=!!v; }
  set replay(v){ this._replay=v||{on:false,t:1}; this._prep(); }
  set selection(id){ if((this._sel&&this._sel.id)===id) return; this._sel=id?(this._data&&this._data.flows.find(f=>f.id===id))||null:null; this._prep(); }
  set hubSelection(id){ if((this._selHub&&this._selHub.id)===id) return; this._selHub=id?(this._data&&this._data.hubs.find(h=>h.id===id))||null:null; this._prep(); }
  _resize(){ const dpr=Math.min(devicePixelRatio||1,2); const w=this.clientWidth,h=this.clientHeight; if(!w||!h) return;
    this.cv.width=w*dpr; this.cv.height=h*dpr; this._dpr=dpr; this._paths=null; }
  _base(lat,lon){ const w=this.clientWidth,h=this.clientHeight;
    return [(lon+180)/360*w, (LAT_TOP-lat)/(LAT_TOP-LAT_BOT)*h]; }
  _buildPaths(){
    const w=this.clientWidth,h=this.clientHeight; if(!w||!h) return;
    const land=new Path2D();
    (this.polys||[]).forEach(rings=>{ rings.forEach(ring=>{
      if(ring.length<3) return;
      for(let i=0;i<ring.length;i++){ const q=this._base(ring[i][1],ring[i][0]);
        i?land.lineTo(q[0],q[1]):land.moveTo(q[0],q[1]); }
      land.closePath(); }); });
    const grat=new Path2D();
    for(let lon=-180;lon<=180;lon+=30){ const a=this._base(LAT_TOP,lon), b=this._base(LAT_BOT,lon);
      grat.moveTo(a[0],a[1]); grat.lineTo(b[0],b[1]); }
    for(let lat=-40;lat<=80;lat+=20){ const a=this._base(lat,-180), b=this._base(lat,180);
      grat.moveTo(a[0],a[1]); grat.lineTo(b[0],b[1]); }
    this._paths={land,grat,w,h};
  }
  _prep(){
    if(!this._data) return;
    const rank=[...this._data.flows].sort((a,b)=>(b.riskN||0)-(a.riskN||0));
    const topIds=this._topN? new Set(rank.slice(0,this._topN).map(f=>f.id)) : null;
    this._vis=this._data.flows.filter(f=>{
      if(this._layers && this._layers[f.ch]===false) return false;
      if(this._sev==='warn' && f.risk==='ok') return false;
      if(this._sev==='crit' && f.risk!=='crit') return false;
      if(this._typ!=='all' && !(f.typ||'').includes(this._typ)) return false;
      if(this._hideNormal && f.risk==='ok') return false;
      if(topIds && !topIds.has(f.id)) return false;
      if(this._replay.on && (f.t0||0)>this._replay.t) return false;
      if(this._selHub && f.sn!==this._selHub.name && f.tn!==this._selHub.name) return false;
      return true;
    });
    this._anim=this._vis.filter(f=>f.risk!=='ok').slice(0,14).map(f=>f.id);
    this._animSet=new Set(this._anim);
  }
  p(lat,lon){ const w=this.clientWidth,h=this.clientHeight;
    const x=(lon+180)/360*w, y=(LAT_TOP-lat)/(LAT_TOP-LAT_BOT)*h;
    return [x*this.k+this.ox, y*this.k+this.oy]; }
  _curve(f){
    const a=this.p(f.slat,f.slon), b=this.p(f.tlat,f.tlon);
    const dx=b[0]-a[0], dy=b[1]-a[1], d=Math.hypot(dx,dy);
    const bend=Math.min(0.26, 0.1+d/(this.clientWidth*6));
    const mx=(a[0]+b[0])/2 - dy*bend, my=(a[1]+b[1])/2 + dx*bend;
    return {a,b,c:[mx,my]};
  }
  _qp(g,t){ const [x0,y0]=g.a,[cx,cy]=g.c,[x1,y1]=g.b; const u=1-t;
    return [u*u*x0+2*u*t*cx+t*t*x1, u*u*y0+2*u*t*cy+t*t*y1]; }
  _width(f){ const v=parseFloat(f.vol)||1; const unit=/B$/.test(f.vol)?1000:1;
    const w=Math.log10(1+v*unit)*1.05; return Math.max(0.7, Math.min(3.4, w)); }
  _events(){
    const el=this.cv; let drag=null;
    el.addEventListener('pointerdown',e=>{ drag={x:e.clientX,y:e.clientY,ox:this.ox,oy:this.oy}; this._moved=false; this.style.cursor='grabbing'; el.setPointerCapture(e.pointerId); });
    el.addEventListener('pointermove',e=>{
      if(drag){ this.ox=drag.ox+(e.clientX-drag.x); this.oy=drag.oy+(e.clientY-drag.y);
        if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>3) this._moved=true; this._clampPan(); }
      else this._hover(e); });
    el.addEventListener('pointerup',e=>{ drag=null; this.style.cursor='grab';
      if(this._moved) return; const hit=this._pick(e);
      if(hit&&hit.hub){ this._selHub=hit.hub; this._sel=null; this._prep(); this.dispatchEvent(new CustomEvent('hubselect',{detail:hit.hub})); }
      else if(hit&&hit.flow){ this._sel=hit.flow; this._selHub=null; this._prep(); this.dispatchEvent(new CustomEvent('flowselect',{detail:hit.flow})); }
      else { this._sel=null; this._selHub=null; this._prep(); this.dispatchEvent(new CustomEvent('clearselect')); } });
    el.addEventListener('dblclick',()=>{ this.reset(); this.dispatchEvent(new CustomEvent('clearselect')); });
    el.addEventListener('wheel',e=>{ e.preventDefault();
      const r=el.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
      const f=e.deltaY<0?1.14:0.88; const nk=Math.min(6,Math.max(1,this.k*f));
      const s=nk/this.k; this.ox=mx-(mx-this.ox)*s; this.oy=my-(my-this.oy)*s; this.k=nk; this._clampPan(); },{passive:false});
    el.addEventListener('mouseleave',()=>{ this.tip.style.display='none'; this._hov=null; });
  }
  _clampPan(){ const w=this.clientWidth,h=this.clientHeight;
    const maxX=0, minX=w-w*this.k, maxY=0, minY=h-h*this.k;
    this.ox=Math.min(maxX,Math.max(minX,this.ox)); this.oy=Math.min(maxY,Math.max(minY,this.oy));
    if(this.k<=1){ this.ox=0; this.oy=0; } }
  reset(){ this.k=1; this.ox=0; this.oy=0; this._sel=null; this._selHub=null; this._prep(); }
  focusRegion(lat,lon,k){ const w=this.clientWidth,h=this.clientHeight; this.k=k||2.6;
    const x=(lon+180)/360*w, y=(LAT_TOP-lat)/(LAT_TOP-LAT_BOT)*h;
    this.ox=w/2-x*this.k; this.oy=h/2-y*this.k; this._clampPan(); }
  shockwave(hubId){ const hb=(this._data&&this._data.hubs||[]).find(h=>h.id===hubId); if(!hb) return;
    this._shocks.push({hb,t:0}); }
  _pick(e){
    const r=this.cv.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
    const hubR=this.k>=1.6?12:9;
    let hubBest=hubR+1, hubHit=null;
    (this._data&&this._data.hubs||[]).forEach(hb=>{ const q=this.p(hb.lat,hb.lon);
      const d=Math.hypot(q[0]-mx,q[1]-my); if(d<hubBest){ hubBest=d; hubHit=hb; } });
    let corBest=8, corHit=null;
    (this._vis||[]).forEach(f=>{ const g2=this._curve(f);
      for(let i=0;i<=22;i++){ const q=this._qp(g2,i/22);
        const d=Math.hypot(q[0]-mx,q[1]-my); if(d<corBest){ corBest=d; corHit=f; } } });
    if(hubHit&&corHit) return hubBest<=corBest+1.5?{hub:hubHit}:{flow:corHit};
    if(hubHit) return {hub:hubHit};
    if(corHit) return {flow:corHit};
    return null;
  }
  _hover(e){
    const hit=this._pick(e); const r=this.getBoundingClientRect();
    const mx=e.clientX-r.left, my=e.clientY-r.top;
    this.style.cursor=hit?'pointer':'grab';
    this._hov=hit?(hit.hub?{hub:hit.hub}:{flow:hit.flow}):null;
    if(hit){
      if(hit.hub){ const hb=hit.hub;
        this.tip.innerHTML='<b style="font-size:12px">'+hb.name+'</b><br><span style="color:#91A4B5">Volume 24h:</span> <b style="font-family:JetBrains Mono,monospace">$'+hb.vol+'</b><br><span style="color:#91A4B5">Inbound / Outbound:</span> <b style="font-family:JetBrains Mono,monospace">'+(hb.inb||0)+' / '+(hb.outb||0)+'</b><br><span style="color:#91A4B5">Entities:</span> <b style="font-family:JetBrains Mono,monospace">'+hb.entities.toLocaleString('vi-VN')+'</b><br><span style="color:#91A4B5">Alerts:</span> <b style="font-family:JetBrains Mono,monospace;color:'+(hb.alerts>20?'#FF4D61':hb.alerts>8?'#F5A524':'#E6F0F8')+'">'+hb.alerts+'</b>';
      } else { const f=hit.flow; const rc=f.risk==='crit'?'#FF4D61':f.risk==='warn'?'#F5A524':'#2DD4A7';
        this.tip.innerHTML='<b style="font-size:12px">'+f.sn+' → '+f.tn+'</b> <span style="font-family:JetBrains Mono,monospace;font-size:9.5px;color:#607487">'+f.id+'</span>'+
          '<br><span style="color:#91A4B5">Channel:</span> '+(CH[f.ch]||{}).n+
          '<br><span style="color:#91A4B5">Flow value:</span> <b style="font-family:JetBrains Mono,monospace">$'+f.vol+'</b> · '+f.txn+' txn'+
          '<br><span style="color:#91A4B5">Risk:</span> <b style="font-family:JetBrains Mono,monospace;color:'+rc+'">'+(f.riskN||'—')+'</b> · alerts '+(f.alertN||0)+
          (f.typ?'<br><span style="color:#91A4B5">'+f.typ+'</span>':'')+
          '<br><span style="color:#607487;font-size:10px">first '+(f.firstSeen||'—')+' · last '+(f.lastSeen||'—')+'</span>';
      }
      this.tip.style.display='block'; const tw=this.tip.offsetWidth;
      let lx=mx+15; if(lx+tw>r.width-4) lx=mx-tw-15;
      this.tip.style.left=lx+'px'; this.tip.style.top=Math.max(4,Math.min(r.height-70,my-18))+'px';
    } else this.tip.style.display='none';
  }
  draw(){
    const w=this.clientWidth,h=this.clientHeight; if(!w||!h||!this._dpr) return;
    const g=this.cv.getContext('2d'); const dpr=this._dpr;
    g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,w,h);
    // sea
    let gr=g.createLinearGradient(0,0,0,h); gr.addColorStop(0,'#08161F'); gr.addColorStop(0.55,'#061119'); gr.addColorStop(1,'#040C13');
    g.fillStyle=gr; g.fillRect(0,0,w,h);
    if(!this._paths||this._paths.w!==w||this._paths.h!==h) this._buildPaths();
    if(this._paths){
      g.save(); g.translate(this.ox,this.oy); g.scale(this.k,this.k);
      g.strokeStyle='rgba(133,173,209,0.05)'; g.lineWidth=1/this.k; g.stroke(this._paths.grat);
      g.fillStyle='#0F2233'; g.fill(this._paths.land);
      g.strokeStyle='rgba(120,178,210,0.32)'; g.lineWidth=Math.min(1.2,0.7+this.k*0.1)/this.k; g.stroke(this._paths.land);
      g.restore();
    }
    const anim=this._animSet||new Set();
    const sel=this._sel, selHub=this._selHub;
    // corridors: normal first, then suspicious, then critical, then selected
    const order=[...(this._vis||[])].sort((a,b)=>{ const s=x=>x.risk==='crit'?3:x.risk==='warn'?2:1; return s(a)-s(b); });
    order.forEach(f=>{
      const g2=this._curve(f); const ch=CH[f.ch]||CH.bank;
      const isSel=sel&&f.id===sel.id;
      const crit=f.risk==='crit', warn=f.risk==='warn';
      const col=crit?'#FF4D61':warn?'#F5A524':ch.c;
      let op=crit?0.85:warn?0.6:0.26;
      if(sel) op=isSel?1:0.07;
      const lw=this._width(f)*(isSel?2.1:crit?1.25:1)*Math.min(1.5,0.85+this.k*0.12);
      g.save();
      g.globalAlpha=op; g.strokeStyle=col; g.lineWidth=lw; g.lineCap='round';
      if(!crit&&!warn&&!isSel) g.setLineDash([5,5]); else g.setLineDash([]);
      if(isSel){ g.shadowColor=col; g.shadowBlur=9; }
      g.beginPath(); g.moveTo(g2.a[0],g2.a[1]); g.quadraticCurveTo(g2.c[0],g2.c[1],g2.b[0],g2.b[1]); g.stroke();
      g.restore();
      // direction arrow at 62%
      if(crit||warn||isSel){
        const p1=this._qp(g2,0.60), p2=this._qp(g2,0.66);
        const ang=Math.atan2(p2[1]-p1[1],p2[0]-p1[0]); const s=isSel?6:4.4;
        g.save(); g.globalAlpha=op; g.fillStyle=col; g.translate(p2[0],p2[1]); g.rotate(ang);
        g.beginPath(); g.moveTo(0,0); g.lineTo(-s,s*0.55); g.lineTo(-s,-s*0.55); g.closePath(); g.fill(); g.restore();
      }
      // moving particle for animated set
      if((anim.has(f.id)||isSel) && !this._reduced){
        const ph=((this.t*(crit?0.30:0.20)+(f.t0||0))%1);
        const q=this._qp(g2,ph);
        g.save(); g.globalAlpha=sel&&!isSel?0.1:1; g.fillStyle=col;
        g.beginPath(); g.arc(q[0],q[1],isSel?3.2:crit?2.6:2.1,0,7); g.fill(); g.restore();
      }
    });
    // shockwaves
    for(let i=this._shocks.length-1;i>=0;i--){ const s=this._shocks[i]; s.t+=0.02*this._speed;
      const q=this.p(s.hb.lat,s.hb.lon); const rr=6+s.t*46;
      g.save(); g.globalAlpha=Math.max(0,0.8*(1-s.t)); g.strokeStyle='#FF4D61'; g.lineWidth=1.6;
      g.beginPath(); g.arc(q[0],q[1],rr,0,7); g.stroke(); g.restore();
      if(s.t>=1) this._shocks.splice(i,1); }
    // hubs
    const hubs=this._data&&this._data.hubs||[];
    const relatedNames=new Set();
    if(selHub){ relatedNames.add(selHub.name); (this._vis||[]).forEach(f=>{ relatedNames.add(f.sn); relatedNames.add(f.tn); }); }
    const placed=[];
    hubs.forEach(hb=>{
      const q=this.p(hb.lat,hb.lon); if(q[0]<-40||q[0]>w+40||q[1]<-30||q[1]>h+30) return;
      const crit=hb.alerts>20, warn=hb.alerts>8;
      const col=crit?'#FF4D61':warn?'#F5A524':'#12D6C5';
      const isSelH=selHub&&selHub.id===hb.id;
      const isHov=this._hov&&this._hov.hub&&this._hov.hub.id===hb.id;
      const dim=selHub&&!relatedNames.has(hb.name)?0.3:1;
      g.save(); g.globalAlpha=dim;
      if(warn&&!this._reduced){ const ph=((this.t*0.35+(hb.size||1)*0.2)%1);
        g.strokeStyle=col; g.globalAlpha=dim*0.45*(1-ph); g.lineWidth=1.1;
        g.beginPath(); g.arc(q[0],q[1],5+ph*13,0,7); g.stroke();
        if(crit){ const p2=((ph+0.5)%1); g.globalAlpha=dim*0.32*(1-p2);
          g.beginPath(); g.arc(q[0],q[1],5+p2*18,0,7); g.stroke(); } }
      g.globalAlpha=dim;
      const rad=3+Math.min(3,(hb.size||1)*0.8)+(isSelH||isHov?1.4:0);
      g.fillStyle=col; if(isSelH||isHov||crit){ g.shadowColor=col; g.shadowBlur=isSelH?12:6; }
      g.beginPath(); g.arc(q[0],q[1],rad,0,7); g.fill(); g.shadowBlur=0;
      g.strokeStyle=isSelH?col:'rgba(230,240,248,0.55)'; g.lineWidth=isSelH?2:0.8;
      g.beginPath(); g.arc(q[0],q[1],rad+(isSelH?4.5:2.6),0,7); g.stroke();
      g.restore();
      // labels: always-on set, or hovered/selected, or zoomed in
      const show=ALWAYS.has(hb.id)||isSelH||isHov||this.k>=1.8||(selHub&&relatedNames.has(hb.name));
      if(!show) return;
      const off=LBL[hb.id]||[9,-11,'left'];
      let lx=q[0]+off[0], ly=q[1]+off[1];
      const label=hb.name, sub='$'+hb.vol;
      g.font='600 10.5px Geist, sans-serif';
      const tw=Math.max(g.measureText(label).width, 30);
      let box={x:off[2]==='right'?lx-tw:lx, y:ly-9, w:tw, h:20};
      let tries=0;
      while(tries<4 && placed.some(p=>!(box.x+box.w<p.x||p.x+p.w<box.x||box.y+box.h<p.y||p.y+p.h<box.y))){
        ly += (tries%2?-1:1)*(15+tries*4); box.y=ly-9; tries++; }
      if(tries>=4&&!isSelH&&!isHov) return;
      placed.push(box);
      g.save(); g.globalAlpha=selHub&&!relatedNames.has(hb.name)?0.35:1;
      // leader line
      g.strokeStyle='rgba(133,173,209,0.35)'; g.lineWidth=0.8;
      g.beginPath(); g.moveTo(q[0],q[1]); g.lineTo(off[2]==='right'?lx+2:lx-2, ly-2); g.stroke();
      g.textAlign=off[2]; g.textBaseline='alphabetic';
      g.fillStyle='rgba(5,11,18,0.62)';
      const pad=3, bx=off[2]==='right'?lx-tw-pad:lx-pad;
      g.fillRect(bx, ly-10, tw+pad*2, 21);
      g.fillStyle=isSelH?'#FFFFFF':'#D4E3EE'; g.font='600 10.5px Geist, sans-serif';
      g.fillText(label, lx, ly);
      g.fillStyle='#8FA4B8'; g.font='9px "JetBrains Mono", monospace';
      g.fillText(sub, lx, ly+10);
      g.restore();
    });
  }
}
customElements.define('fc-worldmap', FCWorldMap);
})();
