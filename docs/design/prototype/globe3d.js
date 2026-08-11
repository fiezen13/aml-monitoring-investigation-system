/* fc-globe3d: WebGL financial-flow globe (three.js, lazy-loaded) with 2D canvas fallback */
(() => {
if (customElements.get('fc-globe3d')) return;
const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js';
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
const CH_CSS = {bank:'#3185FF', p2p:'#12D6C5', vasp:'#A78BFA', chain:'#2DD4A7', gamb:'#F5A524', proj:'#FF8A5C'};
const CH_NAME = {bank:'BANK_TRANSFER', p2p:'P2P_SETTLEMENT', vasp:'VASP_FLOW', chain:'CRYPTO_BRIDGE', gamb:'GAMBLING_SETTLEMENT', proj:'TOKEN_FLOW'};
function ll2a(lat,lon){ const la=lat*Math.PI/180, lo=lon*Math.PI/180; return [Math.cos(la)*Math.sin(lo), Math.sin(la), Math.cos(la)*Math.cos(lo)]; }
function slerpA(a,b,t){ let d=a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; d=Math.min(1,Math.max(-1,d)); const th=Math.acos(d); if(th<1e-4) return a.slice();
  const s=Math.sin(th), w1=Math.sin((1-t)*th)/s, w2=Math.sin(t*th)/s;
  return [a[0]*w1+b[0]*w2, a[1]*w1+b[1]*w2, a[2]*w1+b[2]*w2]; }
class FCGlobe3D extends HTMLElement {
  connectedCallback(){
    ['data','layers','sev','typ','speed','paused','replay','selection'].forEach(p=>{
      if(Object.prototype.hasOwnProperty.call(this,p)){ const v=this[p]; delete this[p]; this[p]=v; } });
    if(this._init){ this._startLoop && this._startLoop(); return; }
    this._init = true;
    this.style.display='block'; this.style.overflow='hidden'; this.style.cursor='grab';
    if(getComputedStyle(this).position==='static') this.style.position='relative';
    this._layers=null; this._sev='all'; this._typ='all'; this._speed=1; this._paused=false;
    this._replay={on:false,t:1}; this._selId=null; this.t=0; this._reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.labelsEl=document.createElement('div'); this.labelsEl.style.cssText='position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:2';
    this.tip=document.createElement('div');
    this.tip.style.cssText='position:absolute;pointer-events:none;background:rgba(10,23,36,0.96);border:1px solid rgba(133,173,209,0.28);border-radius:10px;padding:9px 12px;font:11px Geist,sans-serif;color:#E6F0F8;display:none;z-index:6;line-height:1.55;box-shadow:0 10px 30px rgba(0,0,0,0.5);min-width:180px';
    this.loading=document.createElement('div');
    this.loading.style.cssText='position:absolute;inset:0;display:grid;place-items:center;color:#607487;font:12px Geist,sans-serif;z-index:1';
    this.loading.innerHTML='<div style="text-align:center"><div style="width:34px;height:34px;margin:0 auto 10px;border-radius:50%;border:2px solid rgba(18,214,197,0.15);border-top-color:#12D6C5;animation:fcSpin 0.9s linear infinite"></div>Đang khởi tạo globe 3D…</div><style>@keyframes fcSpin{to{transform:rotate(360deg)}}</style>';
    this.appendChild(this.labelsEl); this.appendChild(this.tip); this.appendChild(this.loading);
    let okGL=false; try{ const c=document.createElement('canvas'); okGL=!!(c.getContext('webgl2')||c.getContext('webgl')); }catch(e){}
    if(!okGL){ this._fallback('WebGL không khả dụng — hiển thị bản 2D'); return; }
    import(THREE_URL).then(T=>{ this.T=T; if(this.isConnected) this._setup(); else this._pendingSetup=true; })
      .catch(()=>this._fallback('Không tải được engine 3D — hiển thị bản 2D'));
  }
  disconnectedCallback(){ if(this._raf){ cancelAnimationFrame(this._raf); this._raf=null; } }
  _fallback(msg){
    this._isFallback=true; this.loading.remove();
    this._fb=document.createElement('fc-globe'); this._fb.style.cssText='position:absolute;inset:0';
    this.insertBefore(this._fb, this.labelsEl);
    if(this._data) this._fb.data=this._data;
    this._fb.addEventListener('hubselect',e=>this.dispatchEvent(new CustomEvent('hubselect',{detail:e.detail})));
    const badge=document.createElement('div');
    badge.style.cssText='position:absolute;top:10px;left:50%;transform:translateX(-50%);background:rgba(245,165,36,0.1);border:1px solid rgba(245,165,36,0.35);color:#F5C97A;font:10.5px Geist,sans-serif;border-radius:20px;padding:3px 12px;z-index:3';
    badge.textContent=msg; this.appendChild(badge);
  }
  set data(v){ this._data=v; if(this._fb){ this._fb.data=v; return; } if(this.scene) this._build(); }
  set layers(v){ this._layers=v; if(this._fb) this._fb.layers=v; this._applyFilters(); }
  set sev(v){ this._sev=v; this._applyFilters(); }
  set typ(v){ this._typ=v; this._applyFilters(); }
  set speed(v){ this._speed=v; if(this._fb) this._fb.speed=v; }
  set paused(v){ this._paused=v; if(this._fb) this._fb.paused=v; }
  set replay(v){ this._replay=v||{on:false,t:1}; this._applyFilters(); }
  set selection(id){ if(this._selId===id) return; this._selId=id; this._applyFilters(); if(!id&&this._camT) this.resetView(false); }
  _setup(){
    const T=this.T;
    this.renderer=new T.WebGLRenderer({antialias:true,alpha:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.8));
    this.renderer.domElement.style.cssText='position:absolute;inset:0;width:100%;height:100%';
    this.insertBefore(this.renderer.domElement, this.labelsEl);
    this.scene=new T.Scene();
    this.camera=new T.PerspectiveCamera(38,1,0.05,20); this.camera.position.set(0,0,2.9); this._zoom=2.9; this._zoomT=2.9;
    this.group=new T.Group(); this.scene.add(this.group);
    this.group.quaternion.setFromAxisAngle(new T.Vector3(0,1,0),-1.2).premultiply(new T.Quaternion().setFromAxisAngle(new T.Vector3(1,0,0),0.35));
    this.scene.add(new T.AmbientLight(0x8FB4D8,0.55));
    const dl=new T.DirectionalLight(0x9FD8E8,0.9); dl.position.set(-2,1.6,2.2); this.scene.add(dl);
    // sphere
    this.group.add(new T.Mesh(new T.SphereGeometry(0.995,64,48), new T.MeshBasicMaterial({color:0x061019})));
    // atmosphere
    const atm=new T.Mesh(new T.SphereGeometry(1.13,48,32), new T.ShaderMaterial({
      side:T.BackSide, transparent:true, blending:T.AdditiveBlending, depthWrite:false,
      vertexShader:'varying vec3 vN;void main(){vN=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
      fragmentShader:'varying vec3 vN;void main(){float i=pow(0.62-dot(vN,vec3(0.0,0.0,1.0)),3.0);gl_FragColor=vec4(0.07,0.55,0.62,1.0)*i*0.55;}'
    }));
    this.scene.add(atm);
    // graticule
    const gPts=[];
    for(let lat=-60;lat<=60;lat+=30) for(let lon=-180;lon<180;lon+=6){ const a=ll2a(lat,lon),b=ll2a(lat,lon+6); gPts.push(a[0],a[1],a[2],b[0],b[1],b[2]); }
    for(let lon=-180;lon<180;lon+=30) for(let lat=-85;lat<85;lat+=5){ const a=ll2a(lat,lon),b=ll2a(lat+5,lon); gPts.push(a[0],a[1],a[2],b[0],b[1],b[2]); }
    const gg=new T.BufferGeometry(); gg.setAttribute('position',new T.Float32BufferAttribute(gPts,3));
    this.group.add(new T.LineSegments(gg,new T.LineBasicMaterial({color:0x85ADD1,transparent:true,opacity:0.06})));
    // land as solid mesh patches per mask cell (clear continent silhouettes)
    const land=(r,c)=>{ if(r<0||r>35) return false; c=((c%72)+72)%72; return MASK[r][c]==='1'; };
    const LAT0=85, DLAT=170/35, DLON=5;
    const pos=[], idx=[]; let vi=0;
    const SUB=2;
    for(let r=0;r<36;r++){ const latT=LAT0-r*DLAT+DLAT/2, latB=LAT0-r*DLAT-DLAT/2;
      for(let c=0;c<72;c++){ if(!land(r,c)) continue;
        const lonL=-180+c*DLON, lonR=lonL+DLON;
        for(let a=0;a<SUB;a++) for(let b=0;b<SUB;b++){
          const la1=latT+(latB-latT)*(a/SUB), la2=latT+(latB-latT)*((a+1)/SUB);
          const lo1=lonL+(lonR-lonL)*(b/SUB), lo2=lonL+(lonR-lonL)*((b+1)/SUB);
          const corners=[[la1,lo1],[la1,lo2],[la2,lo2],[la2,lo1]];
          corners.forEach(([la,lo])=>{ const v=ll2a(Math.max(-89.5,Math.min(89.5,la)),lo); pos.push(v[0]*1.004,v[1]*1.004,v[2]*1.004); });
          idx.push(vi,vi+1,vi+2, vi,vi+2,vi+3); vi+=4;
        } } }
    const lg=new T.BufferGeometry();
    lg.setAttribute('position',new T.Float32BufferAttribute(pos,3));
    lg.setIndex(idx); lg.computeVertexNormals();
    this.group.add(new T.Mesh(lg,new T.MeshBasicMaterial({color:0x35678C,side:T.DoubleSide})));
    // coastline outline
    const cPts=[];
    for(let r=0;r<36;r++) for(let c=0;c<72;c++){ if(!land(r,c)) continue;
      const latT=LAT0-r*DLAT+DLAT/2, latB=LAT0-r*DLAT-DLAT/2, lonL=-180+c*DLON, lonR=lonL+DLON;
      const seg=(la1,lo1,la2,lo2)=>{ const a=ll2a(Math.max(-89.5,Math.min(89.5,la1)),lo1),b=ll2a(Math.max(-89.5,Math.min(89.5,la2)),lo2);
        cPts.push(a[0]*1.008,a[1]*1.008,a[2]*1.008,b[0]*1.008,b[1]*1.008,b[2]*1.008); };
      if(!land(r-1,c)) seg(latT,lonL,latT,lonR);
      if(!land(r+1,c)) seg(latB,lonL,latB,lonR);
      if(!land(r,c-1)) seg(latT,lonL,latB,lonL);
      if(!land(r,c+1)) seg(latT,lonR,latB,lonR); }
    const cg=new T.BufferGeometry(); cg.setAttribute('position',new T.Float32BufferAttribute(cPts,3));
    this.group.add(new T.LineSegments(cg,new T.LineBasicMaterial({color:0x7FCBE8,transparent:true,opacity:0.7,depthWrite:false})));
    this._hubMeshes=[]; this._arcLines=[]; this._labels=[]; this._rings=[]; this._pulses=[];
    this.hubsG=new T.Group(); this.arcsG=new T.Group(); this.fxG=new T.Group();
    this.group.add(this.hubsG); this.group.add(this.arcsG); this.group.add(this.fxG);
    this.ray=new T.Raycaster(); this.ray.params.Line={threshold:0.022}; this._mouse=new T.Vector2();
    this._shocks=[]; this._pulses=[];
    this._events(); this._build();
    this.ro=new ResizeObserver(()=>{ if(this._roQ) return; this._roQ=requestAnimationFrame(()=>{ this._roQ=null; this._resize(); }); });
    this.ro.observe(this); this._resize();
    document.addEventListener('visibilitychange',()=>{ this._hidden=document.hidden; });
    this._startLoop=()=>{ if(this._raf) return;
      const loop=()=>{ if(!this.isConnected){ this._raf=null; return; }
        if(!this._hidden) this._frame(); this._raf=requestAnimationFrame(loop); };
      this._raf=requestAnimationFrame(loop); };
    this.loading.remove(); this._startLoop();
  }
  _resize(){ if(!this.renderer) return; const w=this.clientWidth,h=this.clientHeight; if(!w||!h) return;
    this.renderer.setSize(w,h); this.camera.aspect=w/h; this.camera.updateProjectionMatrix();
  }
  _build(){
    if(!this._data||!this.scene) return; const T=this.T;
    this.hubsG.clear(); this.arcsG.clear(); this.labelsEl.innerHTML='';
    this._hubMeshes=[]; this._arcLines=[]; this._labels=[]; this._rings=[]; this._pulses=[];
    // hubs
    this._data.hubs.forEach(hb=>{
      const v=ll2a(hb.lat,hb.lon); const col=hb.alerts>20?0xFF4D61:hb.alerts>8?0xF5A524:0x12D6C5;
      const m=new T.Mesh(new T.SphereGeometry(0.010+hb.size*0.004,10,8), new T.MeshBasicMaterial({color:col}));
      m.position.set(v[0]*1.005,v[1]*1.005,v[2]*1.005); m.userData.hub=hb;
      this.hubsG.add(m); this._hubMeshes.push(m);
      const halo=new T.Mesh(new T.SphereGeometry((0.010+hb.size*0.004)*1.9,10,8), new T.MeshBasicMaterial({color:col,transparent:true,opacity:0.18,blending:T.AdditiveBlending,depthWrite:false}));
      halo.position.copy(m.position); this.hubsG.add(halo);
      if(hb.alerts>8){ const ring=new T.Mesh(new T.RingGeometry(1,1.14,28), new T.MeshBasicMaterial({color:col,transparent:true,opacity:0.5,side:T.DoubleSide,depthWrite:false}));
        ring.position.copy(m.position); ring.quaternion.setFromUnitVectors(new T.Vector3(0,0,1), new T.Vector3(v[0],v[1],v[2]));
        ring.userData={base:0.018+hb.size*0.005, ph:Math.random()}; this.hubsG.add(ring); this._rings.push(ring); }
      const lb=document.createElement('div');
      lb.style.cssText='position:absolute;transform:translate(8px,-50%);font:600 10px Geist,sans-serif;color:#C7D8E6;white-space:nowrap;text-shadow:0 1px 4px rgba(0,0,0,0.9)';
      lb.innerHTML=hb.name+'<span style="display:block;font:9px \'JetBrains Mono\',monospace;font-weight:400;color:#8FA4B8">$'+hb.vol+'</span>';
      this.labelsEl.appendChild(lb); this._labels.push({el:lb,v,hb});
    });
    // arcs
    this._data.flows.forEach(f=>{
      const a=ll2a(f.slat,f.slon), b=ll2a(f.tlat,f.tlon);
      const d=Math.acos(Math.min(1,a[0]*b[0]+a[1]*b[1]+a[2]*b[2])); const alt=0.045+d*0.16;
      const pts=[]; const N=44;
      for(let i=0;i<=N;i++){ const t=i/N; const v=slerpA(a,b,t); const k=1+alt*Math.sin(t*Math.PI);
        pts.push(new T.Vector3(v[0]*k,v[1]*k,v[2]*k)); }
      const geo=new T.BufferGeometry().setFromPoints(pts);
      const colHex=f.risk==='crit'?0xFF4D61:f.risk==='warn'?0xF5A524:parseInt(CH_CSS[f.ch].slice(1),16);
      const baseOp=f.risk==='crit'?0.85:f.risk==='warn'?0.6:0.22;
      const line=new T.Line(geo,new T.LineBasicMaterial({color:colHex,transparent:true,opacity:baseOp,blending:T.AdditiveBlending,depthWrite:false}));
      line.userData={flow:f,baseOp,pts};
      this.arcsG.add(line); this._arcLines.push(line);
    });
    // pulses: suspicious first, cap 20
    const cand=[...this._arcLines].sort((x,y)=>(y.userData.flow.riskN||0)-(x.userData.flow.riskN||0)).slice(0,20);
    const pg=new T.SphereGeometry(0.0085,6,6);
    cand.forEach(line=>{ const f=line.userData.flow; const susp=f.risk!=='ok';
      const m=new T.Mesh(pg,new T.MeshBasicMaterial({color:line.material.color,transparent:true,opacity:susp?0.95:0.4,blending:T.AdditiveBlending,depthWrite:false}));
      this.fxG.add(m); this._pulses.push({m,line,ph:Math.random(),sp:susp?0.55:0.22}); });
    this._applyFilters();
  }
  _flowVisible(f){
    if(this._layers && this._layers[f.ch]===false) return false;
    if(this._sev==='warn' && f.risk==='ok') return false;
    if(this._sev==='crit' && f.risk!=='crit') return false;
    if(this._typ!=='all' && !(f.typ||'').includes(this._typ)) return false;
    if(this._replay.on && (f.t0||0)>this._replay.t) return false;
    return true;
  }
  _applyFilters(){
    if(!this._arcLines) return;
    this._arcLines.forEach(line=>{ const f=line.userData.flow; const vis=this._flowVisible(f);
      line.visible=vis;
      const selDim=this._selId&&f.id!==this._selId;
      line.material.opacity=this._selId?(f.id===this._selId?1:0.05):line.userData.baseOp; });
    this._pulses&&this._pulses.forEach(p=>{ p.m.visible=p.line.visible&&(!this._selId||p.line.userData.flow.id===this._selId); });
  }
  shockwave(hubId){
    if(!this.scene||this._isFallback) return; const T=this.T;
    const hb=(this._data&&this._data.hubs||[]).find(h=>h.id===hubId); if(!hb) return;
    const v=ll2a(hb.lat,hb.lon);
    const ring=new T.Mesh(new T.RingGeometry(1,1.08,36), new T.MeshBasicMaterial({color:0xFF4D61,transparent:true,opacity:0.85,side:T.DoubleSide,depthWrite:false,blending:T.AdditiveBlending}));
    ring.position.set(v[0]*1.006,v[1]*1.006,v[2]*1.006);
    ring.quaternion.setFromUnitVectors(new T.Vector3(0,0,1), new T.Vector3(v[0],v[1],v[2]));
    this.fxG.add(ring); this._shocks.push({ring,t:0});
  }
  focusFlow(f){
    if(!this.scene) return; const T=this.T;
    const a=ll2a(f.slat,f.slon), b=ll2a(f.tlat,f.tlon); const mid=slerpA(a,b,0.5);
    const local=new T.Vector3(mid[0],mid[1],mid[2]).normalize();
    const world=local.clone().applyQuaternion(this.group.quaternion);
    const target=new T.Quaternion().setFromUnitVectors(world,new T.Vector3(0,0,1)).multiply(this.group.quaternion);
    this._camT={q0:this.group.quaternion.clone(),q1:target,t:0}; this._zoomT=2.15;
  }
  focusHub(hb){ this.focusFlow({slat:hb.lat,slon:hb.lon,tlat:hb.lat,tlon:hb.lon}); this._zoomT=2.3; }
  resetView(clearSel){ this._zoomT=2.9; if(clearSel!==false){ this._selId=null; this._applyFilters(); } }
  _events(){
    const el=this.renderer.domElement; let drag=null;
    el.addEventListener('pointerdown',e=>{ drag={x:e.clientX,y:e.clientY}; this._moved=false; this.style.cursor='grabbing'; el.setPointerCapture(e.pointerId); });
    el.addEventListener('pointermove',e=>{
      if(drag){ const dx=e.clientX-drag.x, dy=e.clientY-drag.y; drag.x=e.clientX; drag.y=e.clientY;
        if(Math.abs(dx)+Math.abs(dy)>1) this._moved=true;
        const T=this.T; const qy=new T.Quaternion().setFromAxisAngle(new T.Vector3(0,1,0),dx*0.0052);
        const qx=new T.Quaternion().setFromAxisAngle(new T.Vector3(1,0,0),dy*0.0038);
        this.group.quaternion.premultiply(qy).premultiply(qx); this._camT=null; this._auto=false; }
      else this._hover(e);
    });
    el.addEventListener('pointerup',e=>{ this.style.cursor='grab';
      if(!this._moved){ const hit=this._pick(e);
        if(hit&&hit.hub){ this.dispatchEvent(new CustomEvent('hubselect',{detail:hit.hub})); this.focusHub(hit.hub); }
        else if(hit&&hit.flow){ this._selId=hit.flow.id; this._applyFilters(); this.focusFlow(hit.flow);
          this.dispatchEvent(new CustomEvent('flowselect',{detail:hit.flow})); } }
      drag=null; });
    el.addEventListener('dblclick',()=>{ this.resetView(); this.dispatchEvent(new CustomEvent('clearselect')); });
    el.addEventListener('wheel',e=>{ e.preventDefault(); this._zoomT=Math.min(4.4,Math.max(1.65,this._zoomT+(e.deltaY>0?0.18:-0.18))); },{passive:false});
    el.addEventListener('mouseleave',()=>{ this.tip.style.display='none'; });
  }
  _pick(e){
    const r=this.renderer.domElement.getBoundingClientRect();
    this._mouse.set(((e.clientX-r.left)/r.width)*2-1, -((e.clientY-r.top)/r.height)*2+1);
    this.ray.setFromCamera(this._mouse,this.camera);
    const hh=this.ray.intersectObjects(this._hubMeshes||[],false);
    if(hh.length) return {hub:hh[0].object.userData.hub};
    const ah=this.ray.intersectObjects((this._arcLines||[]).filter(l=>l.visible),false);
    if(ah.length) return {flow:ah[0].object.userData.flow};
    return null;
  }
  _hover(e){
    const hit=this._pick(e); const r=this.getBoundingClientRect();
    const mx=e.clientX-r.left, my=e.clientY-r.top;
    this.style.cursor=hit?'pointer':'grab';
    if(hit){
      if(hit.hub){ const hb=hit.hub;
        this.tip.innerHTML='<b style="font-size:12px">'+hb.name+'</b><br><span style="color:#91A4B5">Entities:</span> <b style="font-family:JetBrains Mono,monospace">'+hb.entities.toLocaleString('vi-VN')+'</b><br><span style="color:#91A4B5">Alerts mở:</span> <b style="font-family:JetBrains Mono,monospace;color:'+(hb.alerts>20?'#FF4D61':'#E6F0F8')+'">'+hb.alerts+'</b><br><span style="color:#607487;font-size:10px">Click mở hub inspector</span>'; }
      else { const f=hit.flow;
        this.tip.innerHTML='<b style="font-size:12px">'+f.sn+' → '+f.tn+'</b> <span style="font-family:JetBrains Mono,monospace;font-size:9.5px;color:#607487">'+f.id+'</span><br><span style="color:#91A4B5">Kênh:</span> '+CH_NAME[f.ch]+'<br><span style="color:#91A4B5">Volume 24h:</span> <b style="font-family:JetBrains Mono,monospace">$'+f.vol+'</b> · '+f.txn+' txn<br><span style="color:#91A4B5">Risk:</span> <b style="font-family:JetBrains Mono,monospace;color:'+(f.risk==='crit'?'#FF4D61':f.risk==='warn'?'#F5A524':'#2DD4A7')+'">'+(f.riskN||'—')+'</b>'+(f.typ?'<br><span style="color:#91A4B5">'+f.typ+'</span>':''); }
      this.tip.style.display='block'; const tw=this.tip.offsetWidth;
      let lx=mx+14; if(lx+tw>r.width-4) lx=mx-tw-14;
      this.tip.style.left=lx+'px'; this.tip.style.top=Math.max(4,my-16)+'px';
    } else this.tip.style.display='none';
  }
  _frame(){
    const T=this.T; const dt=0.016;
    if(!this._paused&&!this._reduced) this.t+=dt*this._speed;
    if(this._auto!==false&&!this._reduced&&!this._selId){
      this.group.quaternion.premultiply(new T.Quaternion().setFromAxisAngle(new T.Vector3(0,1,0),0.0006*this._speed)); }
    if(this._camT){ this._camT.t+=dt*1.6; const k=Math.min(1,this._camT.t); const e=1-Math.pow(1-k,3);
      this.group.quaternion.slerpQuaternions(this._camT.q0,this._camT.q1,e); if(k>=1) this._camT=null; }
    this._zoom+=(this._zoomT-this._zoom)*0.08; this.camera.position.z=this._zoom;
    // pulses
    this._pulses.forEach(p=>{ if(!p.m.visible) return;
      p.ph=(p.ph+dt*p.sp*this._speed)%1;
      const pts=p.line.userData.pts; const i=Math.min(pts.length-1,Math.floor(p.ph*(pts.length-1)));
      p.m.position.copy(pts[i]); });
    // alert rings
    this._rings.forEach(rg=>{ const k=((this.t*0.9+rg.userData.ph)%1);
      const s=rg.userData.base*(1+k*2.2); rg.scale.set(s,s,s); rg.material.opacity=0.5*(1-k); });
    // shockwaves (one-shot)
    for(let i=this._shocks.length-1;i>=0;i--){ const s=this._shocks[i]; s.t+=dt*0.9;
      const sc=0.02+s.t*0.14; s.ring.scale.set(sc,sc,sc); s.ring.material.opacity=0.85*(1-s.t);
      if(s.t>=1){ this.fxG.remove(s.ring); this._shocks.splice(i,1); } }
    // labels
    if(this._labels){ const w=this.clientWidth,h=this.clientHeight; const v=new T.Vector3();
      this._labels.forEach(L=>{ v.set(L.v[0],L.v[1],L.v[2]).applyQuaternion(this.group.quaternion);
        const front=v.z>0.18; if(!front){ L.el.style.display='none'; return; }
        const p=v.clone().project(this.camera);
        L.el.style.display='block'; L.el.style.opacity=String(0.35+v.z*0.65);
        L.el.style.left=((p.x+1)/2*w)+'px'; L.el.style.top=((-p.y+1)/2*h)+'px'; }); }
    this.renderer.render(this.scene,this.camera);
  }
}
customElements.define('fc-globe3d', FCGlobe3D);
})();
