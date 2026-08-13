/* fc-chart — unified enterprise chart engine (canvas)
   types: line | area | bars | stackbars | stackarea | hbars | donut | heat | sankey | spark | waterfall | funnel | percentile
   shared: tabular-number tooltip, legend data, zoom+brush, compare-period overlay, click cross-filter, ref lines, markers */
(() => {
if (customElements.get('fc-chart')) return;
const PAL={grid:'rgba(133,173,209,0.06)',txt:'#91A2B1',mut:'#8397A8',cyan:'#20C7A7',blue:'#4B9EFF',amber:'#F0B44D',red:'#F45B69',green:'#4CC38A',purple:'#A78BFA'};
const SC=[PAL.blue,PAL.purple,PAL.green,PAL.amber,PAL.red,PAL.cyan];
const MONO='"JetBrains Mono", monospace', SANS='Geist, sans-serif';
function fmt(n,d){ if(n==null||isNaN(n)) return '—';
  const a=Math.abs(n); const s=n<0?'-':'';
  if(a>=1e9) return s+(a/1e9).toFixed(2)+'B'; if(a>=1e6) return s+(a/1e6).toFixed(1)+'M';
  if(a>=1e3) return s+(a/1e3).toFixed(1)+'K';
  return s+(d!=null?a.toFixed(d):(Math.round(a*100)/100).toString()); }
function nf(n){ return (n==null||isNaN(n))?'—':n.toLocaleString('vi-VN',{maximumFractionDigits:2}); }
class FCChart extends HTMLElement {
  static get observedAttributes(){ return ['spec']; }
  connectedCallback(){
    ['data','spec'].forEach(p=>{ if(Object.prototype.hasOwnProperty.call(this,p)){ const v=this[p]; delete this[p]; this[p]=v; } });
    if(this._init) return; this._init=true;
    this.style.display='block'; this.style.minHeight='36px';
    if(getComputedStyle(this).position==='static') this.style.position='relative';
    this.cv=document.createElement('canvas'); this.cv.style.cssText='width:100%;height:100%;display:block';
    this.tip=document.createElement('div');
    this.tip.style.cssText='position:absolute;pointer-events:none;background:#0A1017;border:1px solid rgba(133,173,209,0.28);border-radius:8px;padding:7px 10px;font:11px '+SANS+';color:#E6EDF3;display:none;z-index:5;white-space:nowrap;box-shadow:0 10px 26px rgba(0,0,0,0.5);line-height:1.55';
    this.appendChild(this.cv); this.appendChild(this.tip);
    this.hi=-1; this._zoom=null; this._brush=null;
    this.ro=new ResizeObserver(()=>{ if(this._roQ) return; this._roQ=requestAnimationFrame(()=>{ this._roQ=null; this.draw(); }); });
    this.ro.observe(this);
    this.cv.addEventListener('mousemove',e=>this.hover(e));
    this.cv.addEventListener('mouseleave',()=>{ this.hi=-1; this.tip.style.display='none'; this.draw();
      this.dispatchEvent(new CustomEvent('hoverindex',{detail:{index:-1}})); });
    this.cv.addEventListener('mousedown',e=>this._down(e));
    window.addEventListener('mouseup',this._up=(e)=>this._endBrush(e));
    this.cv.addEventListener('dblclick',()=>{ this._zoom=null; this.draw(); });
    this.cv.addEventListener('click',()=>{ if(this._dragged) return;
      if(this.hi>=0&&this._spec) this.dispatchEvent(new CustomEvent('pick',{detail:this._detail(this.hi)})); });
    if(this.getAttribute('spec')) this.attributeChangedCallback();
    this.draw();
  }
  disconnectedCallback(){ window.removeEventListener('mouseup',this._up); }
  attributeChangedCallback(){ try{ this._spec=JSON.parse(this.getAttribute('spec')); this._zoom=null; }catch(e){} if(this._init) this.draw(); }
  set data(v){ this._spec=v; this._zoom=null; if(this._init) this.draw(); }
  get data(){ return this._spec; }
  set hoverIndex(i){ if(this.hi===i) return; this.hi=i==null?-1:i; if(this._init) this.draw(); }
  get legend(){ const s=this._spec; if(!s) return [];
    if(s.series) return s.series.map((se,k)=>({name:se.name,color:se.color||SC[k]}));
    if(s.items) return s.items.map((it,i)=>({name:it.label,color:it.color||SC[i%6]}));
    return []; }
  get tableData(){ const s=this._spec; if(!s) return {cols:[],rows:[]};
    if(s.series&&s.labels) return {cols:['Kỳ',...s.series.map(x=>x.name)],
      rows:s.labels.map((l,i)=>[l,...s.series.map(x=>nf(x.data[i]))])};
    if(s.items) return {cols:['Hạng mục','Giá trị'],rows:s.items.map(it=>[it.label,nf(it.value)])};
    if(s.type==='heat') return {cols:['Ngày',...s.cols],rows:s.rows.map((r,i)=>[r,...s.data[i].map(nf)])};
    if(s.type==='sankey') return {cols:['Nút','Cột'],rows:s.nodes.map(n=>[n.name,String(n.col)])};
    return {cols:[],rows:[]}; }
  exportPNG(name){ try{ const a=document.createElement('a'); a.download=(name||'chart')+'.png'; a.href=this.cv.toDataURL('image/png'); a.click(); return true; }catch(e){ return false; } }
  // ===== interaction =====
  _idxAt(mx){ const g=this.geo; if(!g||g.x1==null) return -1; const n=this._n();
    const r=this._range(); const t=(mx-g.x0)/(g.x1-g.x0);
    const i=Math.round(r.a+t*(r.b-r.a)); return (i>=0&&i<n)?i:-1; }
  _n(){ const s=this._spec; if(!s) return 0;
    if(s.labels) return s.labels.length; if(s.series&&s.series[0]) return s.series[0].data.length; return 0; }
  _range(){ const n=this._n(); if(this._zoom) return {a:this._zoom[0],b:this._zoom[1]}; return {a:0,b:n-1}; }
  _down(e){ const s=this._spec; if(!s||!/line|area|bars|stackbars|stackarea/.test(s.type)) return;
    const r=this.cv.getBoundingClientRect(); this._brush={x0:e.clientX-r.left,x1:e.clientX-r.left}; this._dragged=false; }
  _endBrush(){ const b=this._brush; this._brush=null;
    if(!b||Math.abs(b.x1-b.x0)<12){ this.draw(); return; }
    const i0=this._idxAt(Math.min(b.x0,b.x1)), i1=this._idxAt(Math.max(b.x0,b.x1));
    if(i0>=0&&i1>i0){ this._zoom=[i0,i1];
      this.dispatchEvent(new CustomEvent('brush',{detail:{from:i0,to:i1,labels:(this._spec.labels||[]).slice(i0,i1+1)}})); }
    this._dragged=true; setTimeout(()=>this._dragged=false,60); this.draw(); }
  _detail(i){ const s=this._spec;
    if(s.type==='heat'){ const c=i%s.cols.length, r=Math.floor(i/s.cols.length);
      return {index:i,row:s.rows[r],col:s.cols[c],value:s.data[r][c]}; }
    if(s.items) return {index:i,label:s.items[i]&&s.items[i].label,value:s.items[i]&&s.items[i].value};
    return {index:i,label:s.labels&&s.labels[i],values:(s.series||[]).map(x=>x.data[i])}; }
  hover(e){
    const s=this._spec; if(!s) return;
    const r=this.cv.getBoundingClientRect(); const mx=e.clientX-r.left,my=e.clientY-r.top;
    if(this._brush){ this._brush.x1=mx; this.draw(); return; }
    let hi=-1,html='';
    const t=s.type;
    if(/line|area|bars|stackbars|stackarea/.test(t)){
      hi=this._idxAt(mx);
      if(hi>=0){ html='<b style="color:#E6EDF3">'+(s.labels?s.labels[hi]:hi)+'</b>';
        s.series.forEach((se,k)=>{ if(se.hidden) return;
          html+='<br><span style="color:'+(se.color||SC[k])+'">●</span> '+se.name+': <b style="font-family:'+MONO+';font-variant-numeric:tabular-nums">'+(se.fmt==='raw'?nf(se.data[hi]):fmt(se.data[hi]))+(se.unit||s.unit||'')+'</b>'; });
        if(s.compare&&s.compare.series) s.compare.series.forEach((se,k)=>{
          html+='<br><span style="color:#8397A8">◌</span> '+se.name+': <b style="font-family:'+MONO+';color:#91A2B1">'+fmt(se.data[hi])+(s.unit||'')+'</b>'; }); } }
    else if(t==='hbars'||t==='funnel'||t==='waterfall'){
      const bh=this.geo.bh; const i=Math.floor((my-this.geo.y0)/bh);
      const list=s.items||[];
      if(i>=0&&i<list.length){ hi=i; const it=list[i];
        html='<b>'+it.label+'</b>: <b style="font-family:'+MONO+'">'+nf(it.value)+(s.unit||'')+'</b>'+
          (it.target!=null?'<br><span style="color:#91A2B1">Yêu cầu: <b style="font-family:'+MONO+'">'+nf(it.target)+(s.unit||'')+'</b></span>':'')+
          (it.pctOfPrev?'<br><span style="color:#91A2B1">'+it.pctOfPrev+'</span>':'')+
          (it.sub?'<br><span style="color:#8397A8">'+it.sub+'</span>':''); } }
    else if(t==='donut'){ const {cx,cy,R,r:ri}=this.geo; const dx=mx-cx,dy=my-cy,d=Math.hypot(dx,dy);
      if(d>ri&&d<R){ let a=Math.atan2(dy,dx)+Math.PI/2; if(a<0)a+=Math.PI*2;
        const tot=s.items.reduce((p,c)=>p+c.value,0); let acc=0;
        for(let i=0;i<s.items.length;i++){ acc+=s.items[i].value/tot*Math.PI*2;
          if(a<acc){ hi=i; const it=s.items[i];
            html='<b>'+it.label+'</b>: <b style="font-family:'+MONO+'">'+nf(it.value)+(s.unit||'')+'</b> · '+Math.round(it.value/tot*100)+'%'; break; } } } }
    else if(t==='heat'){ const {x0,y0,cw,ch}=this.geo; const c=Math.floor((mx-x0)/cw),rr=Math.floor((my-y0)/ch);
      if(c>=0&&c<s.cols.length&&rr>=0&&rr<s.rows.length){ hi=rr*s.cols.length+c;
        html='<b>'+s.rows[rr]+' · '+s.cols[c]+'</b>: <b style="font-family:'+MONO+'">'+nf(s.data[rr][c])+(s.unit||'')+'</b><br><span style="color:#8397A8;font-size:10px">click để lọc bảng</span>'; } }
    else if(t==='sankey'){ (this.geo.nodes||[]).forEach((nd,i)=>{
        if(mx>=nd.x&&mx<=nd.x+nd.w&&my>=nd.y&&my<=nd.y+nd.h){ hi=i;
          html='<b>'+nd.name+'</b>: <b style="font-family:'+MONO+'">'+fmt(nd.total)+(s.unit||'')+'</b>'; } }); }
    else if(t==='percentile'){ const rows=s.items||[]; const bh=this.geo.bh;
      const i=Math.floor((my-this.geo.y0)/bh);
      if(i>=0&&i<rows.length){ hi=i; const it=rows[i];
        html='<b>'+it.label+'</b><br><span style="color:#91A2B1">Entity:</span> <b style="font-family:'+MONO+'">'+nf(it.value)+(it.unit||'')+'</b> · percentile <b style="color:'+(it.pct>=95?'#FF8792':it.pct>=80?'#F0B44D':'#4CC38A')+'">'+it.pct+'</b>'+
          '<br><span style="color:#8397A8">Peer p50 '+nf(it.p50)+' · p95 '+nf(it.p95)+'</span>'; } }
    if(hi!==this.hi){ this.hi=hi; this.draw();
      this.dispatchEvent(new CustomEvent('hoverindex',{detail:{index:hi,group:s.syncGroup||null}})); }
    if(hi>=0&&html){ this.tip.innerHTML=html; this.tip.style.display='block';
      const tw=this.tip.offsetWidth; let lx=mx+14; if(lx+tw>r.width) lx=Math.max(2,mx-tw-14);
      this.tip.style.left=lx+'px'; this.tip.style.top=Math.max(2,Math.min(r.height-40,my-14))+'px'; }
    else this.tip.style.display='none';
  }
  // ===== draw =====
  draw(){
    if(!this._styleFixed){ this._styleFixed=1; this.style.display='block';
      if(getComputedStyle(this).position==='static') this.style.position='relative'; }
    const s=this._spec; const w=this.clientWidth,h=this.clientHeight; if(!w||!h) return;
    const dpr=Math.min(devicePixelRatio||1,2); this.cv.width=w*dpr; this.cv.height=h*dpr;
    const g=this.cv.getContext('2d'); g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,w,h);
    if(!s) return;
    g.font='10px '+SANS; g.textBaseline='middle'; this.geo={};
    const t=s.type;
    if(t==='line'||t==='area') this.dLine(g,w,h,s);
    else if(t==='stackarea') this.dLine(g,w,h,s,true);
    else if(t==='bars'||t==='stackbars') this.dBars(g,w,h,s);
    else if(t==='hbars') this.dHBars(g,w,h,s);
    else if(t==='waterfall') this.dWaterfall(g,w,h,s);
    else if(t==='funnel') this.dFunnel(g,w,h,s);
    else if(t==='percentile') this.dPercentile(g,w,h,s);
    else if(t==='donut') this.dDonut(g,w,h,s);
    else if(t==='heat') this.dHeat(g,w,h,s);
    else if(t==='sankey') this.dSankey(g,w,h,s);
    else if(t==='spark') this.dSpark(g,w,h,s);
    // brush overlay
    if(this._brush&&this.geo.x0!=null){ const b=this._brush;
      g.fillStyle='rgba(18,214,197,0.12)'; g.strokeStyle='rgba(18,214,197,0.5)'; g.lineWidth=1;
      const x=Math.min(b.x0,b.x1), bw=Math.abs(b.x1-b.x0);
      g.fillRect(x,this.geo.y0,bw,this.geo.y1-this.geo.y0); g.strokeRect(x,this.geo.y0,bw,this.geo.y1-this.geo.y0); }
    if(this._zoom){ g.fillStyle='rgba(18,214,197,0.10)'; g.strokeStyle='rgba(18,214,197,0.35)';
      const bw=g.measureText('zoom · dbl-click reset').width+10;
      g.fillRect(w-bw-6,4,bw,15); g.strokeRect(w-bw-6,4,bw,15);
      g.fillStyle='#86DCB4'; g.textAlign='left'; g.font='9px '+SANS; g.fillText('zoom · dbl-click reset',w-bw-1,12); }
  }
  frame(g,w,h,s,maxV,minV){
    const lo=minV||0;
    const yl=[fmt(maxV),fmt(lo)].reduce((a,b)=>g.measureText(a).width>g.measureText(b).width?a:b);
    const padL=s.hideY?8:Math.max(26,g.measureText(yl).width+12);
    const padR=s.y2?Math.max(28,g.measureText(fmt(s.y2max||maxV)).width+10):8;
    const x0=padL,x1=w-padR,y0=6,y1=h-(s.labels?17:6);
    g.strokeStyle=PAL.grid; g.fillStyle=PAL.mut; g.lineWidth=1; g.textAlign='right'; g.font='9.5px '+MONO;
    for(let i=0;i<=4;i++){ const y=y1-(y1-y0)*i/4;
      g.beginPath(); g.moveTo(x0,y+.5); g.lineTo(x1,y+.5); g.stroke();
      if(!s.hideY) g.fillText(fmt(lo+(maxV-lo)*i/4),x0-5,y); }
    if(s.y2){ g.textAlign='left'; g.fillStyle='rgba(167,139,250,0.85)';
      for(let i=0;i<=4;i++){ const y=y1-(y1-y0)*i/4; g.fillText(fmt((s.y2max||maxV)*i/4),x1+4,y); } }
    if(s.labels){ g.font='9.5px '+SANS; g.textAlign='center'; g.fillStyle=PAL.mut;
      const r=this._range(); const cnt=r.b-r.a+1;
      const step=Math.max(1,Math.ceil(cnt/Math.max(2,Math.floor((x1-x0)/58))));
      for(let i=r.a;i<=r.b;i+=step){ const px=x0+(x1-x0)*((i-r.a)/Math.max(1,cnt-1));
        g.fillText(s.labels[i],px,y1+9); } }
    g.font='10px '+SANS;
    return {x0,x1,y0,y1};
  }
  _xs(i){ const r=this._range(); const {x0,x1}=this.geo; const cnt=r.b-r.a+1;
    return x0+(x1-x0)*((i-r.a)/Math.max(1,cnt-1)); }
  dLine(g,w,h,s,stack){
    const r=this._range(); const slice=a=>a.slice(r.a,r.b+1);
    const act=s.series.filter(x=>!x.hidden);
    let maxV;
    if(stack){ const n=this._n(); let m=0;
      for(let i=r.a;i<=r.b;i++){ let sum=0; act.forEach(x=>sum+=x.data[i]||0); m=Math.max(m,sum); } maxV=s.max||m*1.12||1; }
    else maxV=s.max||Math.max(...act.flatMap(x=>slice(x.data)))*1.15||1;
    const geo=this.frame(g,w,h,s,maxV,s.min); this.geo=geo; const {x0,x1,y0,y1}=geo;
    const lo=s.min||0; const yv=v=>y1-(y1-y0)*Math.min(1,Math.max(0,(v-lo)/(maxV-lo)));
    // reference lines
    (s.refs||[]).forEach(rf=>{ const y=yv(rf.v); g.strokeStyle=rf.color||'rgba(133,173,209,0.35)'; g.setLineDash([4,4]);
      g.beginPath(); g.moveTo(x0,y); g.lineTo(x1,y); g.stroke(); g.setLineDash([]);
      if(rf.label){ g.fillStyle=rf.color||PAL.mut; g.textAlign='left'; g.font='9px '+SANS; g.fillText(rf.label,x0+4,y-6); g.font='10px '+SANS; } });
    // compare period (ghost)
    if(s.compare&&s.compare.series) s.compare.series.forEach(se=>{
      g.beginPath(); for(let i=r.a;i<=r.b;i++){ const px=this._xs(i),py=yv(se.data[i]); i===r.a?g.moveTo(px,py):g.lineTo(px,py); }
      g.strokeStyle='rgba(133,173,209,0.45)'; g.lineWidth=1; g.setLineDash([3,3]); g.stroke(); g.setLineDash([]); });
    if(stack){
      const acc=new Array(this._n()).fill(0);
      act.forEach((se,k)=>{ const col=se.color||SC[k];
        g.beginPath();
        for(let i=r.a;i<=r.b;i++){ const px=this._xs(i); const py=yv(acc[i]+se.data[i]); i===r.a?g.moveTo(px,py):g.lineTo(px,py); }
        for(let i=r.b;i>=r.a;i--){ const px=this._xs(i); g.lineTo(px,yv(acc[i])); }
        g.closePath(); g.fillStyle=col+'8A'; g.fill(); g.strokeStyle=col; g.lineWidth=1.2; g.stroke();
        for(let i=r.a;i<=r.b;i++) acc[i]+=se.data[i]; });
    } else {
      act.forEach((se,k)=>{ const col=se.color||SC[k];
        const y2=se.axis===2; const m2=s.y2max||maxV;
        const yy=v=>y2?(y1-(y1-y0)*Math.min(1,v/m2)):yv(v);
        if(s.type==='area'||se.fill){ g.beginPath(); g.moveTo(this._xs(r.a),y1);
          for(let i=r.a;i<=r.b;i++) g.lineTo(this._xs(i),yy(se.data[i]));
          g.lineTo(this._xs(r.b),y1); g.closePath();
          const gr=g.createLinearGradient(0,y0,0,y1); gr.addColorStop(0,col+'44'); gr.addColorStop(1,col+'00'); g.fillStyle=gr; g.fill(); }
        g.beginPath(); for(let i=r.a;i<=r.b;i++){ const px=this._xs(i),py=yy(se.data[i]); i===r.a?g.moveTo(px,py):g.lineTo(px,py); }
        g.strokeStyle=col; g.lineWidth=se.width||1.6; g.setLineDash(se.dash?[4,3]:[]); g.stroke(); g.setLineDash([]);
        if(se.dots){ for(let i=r.a;i<=r.b;i++){ g.beginPath(); g.arc(this._xs(i),yy(se.data[i]),2.2,0,7); g.fillStyle=col; g.fill(); } } });
    }
    // event markers
    (s.marks||[]).forEach(mk=>{ if(mk.i<r.a||mk.i>r.b) return; const px=this._xs(mk.i);
      g.strokeStyle=mk.color||PAL.red; g.setLineDash([2,3]); g.beginPath(); g.moveTo(px,y0); g.lineTo(px,y1); g.stroke(); g.setLineDash([]);
      g.beginPath(); g.arc(px,y0+4,3.4,0,7); g.fillStyle=mk.color||PAL.red; g.fill(); });
    if(this.hi>=r.a&&this.hi<=r.b){ const hx=this._xs(this.hi);
      g.strokeStyle='rgba(230,240,248,0.28)'; g.beginPath(); g.moveTo(hx,y0); g.lineTo(hx,y1); g.stroke();
      act.forEach((se,k)=>{ const y2=se.axis===2; const m2=s.y2max||maxV;
        const py=y2?(y1-(y1-y0)*Math.min(1,se.data[this.hi]/m2)):yv(se.data[this.hi]);
        g.beginPath(); g.arc(hx,py,3.5,0,7); g.fillStyle=se.color||SC[k]; g.fill(); }); }
  }
  dBars(g,w,h,s){
    const stacked=s.type==='stackbars'; const r=this._range(); const act=s.series.filter(x=>!x.hidden);
    let maxV;
    if(stacked){ let m=0; for(let i=r.a;i<=r.b;i++){ let sum=0; act.forEach(x=>sum+=x.data[i]); m=Math.max(m,sum); } maxV=s.max||m*1.12||1; }
    else maxV=s.max||Math.max(...act.flatMap(x=>x.data.slice(r.a,r.b+1)))*1.12||1;
    const geo=this.frame(g,w,h,s,maxV); this.geo=geo; const {x0,x1,y0,y1}=geo;
    const cnt=r.b-r.a+1; const slot=(x1-x0)/cnt; const bw=Math.min(28,slot*0.64);
    for(let i=r.a;i<=r.b;i++){ let acc=0; const bx=x0+slot*(i-r.a)+slot/2;
      act.forEach((se,k)=>{ const col=se.color||SC[k]; const bh=(y1-y0)*Math.min(1,se.data[i]/maxV);
        g.fillStyle=this.hi===i?col:col+'CC';
        if(stacked){ g.fillRect(bx-bw/2,y1-acc-bh,bw,bh); acc+=bh; }
        else { const sw=bw/act.length; g.fillRect(bx-bw/2+sw*k,y1-bh,Math.max(1,sw-1),bh); } }); }
  }
  dHBars(g,w,h,s){
    const items=s.items; const maxV=s.max||Math.max(...items.map(i=>Math.max(Math.abs(i.value),i.target||0)))*1.06||1;
    const natural=Math.max(...items.map(i=>g.measureText(i.label).width))+14;
    const lw=Math.max(34,Math.min(160,natural,w*0.44));
    const valW=(w-lw)<70?0:44;
    const x0=lw,x1=Math.max(lw+18,w-valW-4),y0=4; const bh=Math.min(30,(h-8)/items.length);
    this.geo={x0,y0,bh,x1,y1:y0+bh*items.length};
    const clip=(t,m)=>{ if(g.measureText(t).width<=m) return t; while(t.length>1&&g.measureText(t+'…').width>m) t=t.slice(0,-1); return t+'…'; };
    items.forEach((it,i)=>{ const y=y0+bh*i; const col=it.color||SC[i%6];
      g.fillStyle=this.hi===i?'#E6EDF3':PAL.txt; g.textAlign='right'; g.font='10px '+SANS;
      g.fillText(clip(it.label,lw-8),lw-8,y+bh/2);
      g.fillStyle='rgba(133,173,209,0.05)'; g.fillRect(x0,y+bh*0.24,x1-x0,bh*0.52);
      const bwv=(x1-x0)*Math.min(1,Math.abs(it.value)/maxV);
      g.fillStyle=this.hi===i?col:col+'CC'; g.fillRect(x0,y+bh*0.24,bwv,bh*0.52);
      if(it.target!=null){ const tx=x0+(x1-x0)*Math.min(1,it.target/maxV);
        g.strokeStyle='#E6EDF3'; g.lineWidth=1.4; g.beginPath(); g.moveTo(tx,y+bh*0.14); g.lineTo(tx,y+bh*0.86); g.stroke(); }
      if(valW){ g.fillStyle='#E6EDF3'; g.textAlign='left'; g.font='10px '+MONO;
        g.fillText((it.value<0?'−':'')+fmt(Math.abs(it.value))+(s.unit||''),Math.min(x1+4,x0+bwv+6),y+bh/2); } });
    g.font='10px '+SANS;
  }
  dWaterfall(g,w,h,s){
    const items=s.items; let run=0; const tots=[];
    items.forEach(it=>{ if(it.total){ tots.push({from:0,to:it.value}); run=it.value; } else { tots.push({from:run,to:run+it.value}); run+=it.value; } });
    const maxV=s.max||Math.max(...tots.map(t=>Math.max(t.from,t.to)))*1.1||1;
    const natural=Math.max(...items.map(i=>g.measureText(i.label).width))+14;
    const lw=Math.max(34,Math.min(150,natural,w*0.42)); const valW=(w-lw)<70?0:44;
    const x0=lw,x1=Math.max(lw+18,w-valW-4),y0=4; const bh=Math.min(28,(h-8)/items.length);
    this.geo={x0,y0,bh,x1,y1:y0+bh*items.length};
    const clip=(t,m)=>{ if(g.measureText(t).width<=m) return t; while(t.length>1&&g.measureText(t+'…').width>m) t=t.slice(0,-1); return t+'…'; };
    items.forEach((it,i)=>{ const y=y0+bh*i; const seg=tots[i];
      const col=it.total?'#20C7A7':(it.value<0?PAL.red:(it.color||SC[i%6]));
      g.fillStyle=this.hi===i?'#E6EDF3':PAL.txt; g.textAlign='right'; g.font='10px '+SANS; g.fillText(clip(it.label,lw-8),lw-8,y+bh/2);
      const xa=x0+(x1-x0)*Math.min(1,Math.min(seg.from,seg.to)/maxV);
      const xb=x0+(x1-x0)*Math.min(1,Math.max(seg.from,seg.to)/maxV);
      g.fillStyle='rgba(133,173,209,0.05)'; g.fillRect(x0,y+bh*0.26,x1-x0,bh*0.48);
      g.fillStyle=this.hi===i?col:col+'CC'; g.fillRect(xa,y+bh*0.26,Math.max(1.5,xb-xa),bh*0.48);
      if(i<items.length-1&&!items[i+1].total){ g.strokeStyle='rgba(133,173,209,0.3)'; g.setLineDash([2,2]);
        g.beginPath(); g.moveTo(xb,y+bh*0.74); g.lineTo(xb,y+bh*1.26); g.stroke(); g.setLineDash([]); }
      if(valW){ g.fillStyle=it.total?'#86DCB4':'#E6EDF3'; g.textAlign='left'; g.font='10px '+MONO;
        g.fillText((it.value<0?'−':it.total?'=':'+')+fmt(Math.abs(it.value))+(s.unit||''),Math.min(x1+4,xb+6),y+bh/2); } });
    g.font='10px '+SANS;
  }
  dFunnel(g,w,h,s){
    const items=s.items; const maxV=items[0]?items[0].value:1;
    const natural=Math.max(...items.map(i=>g.measureText(i.label).width))+14;
    const lw=Math.max(34,Math.min(160,natural,w*0.42)); const valW=(w-lw)<80?0:66;
    const x0=lw,x1=Math.max(lw+18,w-valW-4),y0=4; const bh=Math.min(30,(h-8)/items.length);
    this.geo={x0,y0,bh,x1,y1:y0+bh*items.length};
    const clip=(t,m)=>{ if(g.measureText(t).width<=m) return t; while(t.length>1&&g.measureText(t+'…').width>m) t=t.slice(0,-1); return t+'…'; };
    items.forEach((it,i)=>{ const y=y0+bh*i; const col=it.color||SC[i%6];
      const frac=Math.min(1,it.value/maxV); const bwv=(x1-x0)*frac;
      const cx=(x0+x1)/2;
      g.fillStyle=this.hi===i?'#E6EDF3':PAL.txt; g.textAlign='right'; g.font='10px '+SANS; g.fillText(clip(it.label,lw-8),lw-8,y+bh/2);
      g.fillStyle=this.hi===i?col:col+'C4';
      g.fillRect(cx-bwv/2,y+bh*0.2,bwv,bh*0.6);
      const prev=i>0?items[i-1].value:it.value;
      it.pctOfPrev=i>0?('so bước trước: '+Math.round(it.value/prev*100)+'%'):'100% baseline';
      if(valW){ g.fillStyle='#E6EDF3'; g.textAlign='left'; g.font='10px '+MONO;
        g.fillText(nf(it.value)+'  '+Math.round(frac*100)+'%',x1+4,y+bh/2); } });
    g.font='10px '+SANS;
  }
  dPercentile(g,w,h,s){
    const items=s.items;
    const natural=Math.max(...items.map(i=>g.measureText(i.label).width))+14;
    const lw=Math.max(34,Math.min(160,natural,w*0.40)); const valW=(w-lw)<90?0:52;
    const x0=lw,x1=Math.max(lw+20,w-valW-6),y0=6; const bh=Math.min(34,(h-10)/items.length);
    this.geo={x0,y0,bh,x1,y1:y0+bh*items.length};
    const clip=(t,m)=>{ if(g.measureText(t).width<=m) return t; while(t.length>1&&g.measureText(t+'…').width>m) t=t.slice(0,-1); return t+'…'; };
    items.forEach((it,i)=>{ const y=y0+bh*i+bh/2;
      g.fillStyle=this.hi===i?'#E6EDF3':PAL.txt; g.textAlign='right'; g.font='10px '+SANS; g.fillText(clip(it.label,lw-8),lw-8,y);
      // peer distribution band p25–p95
      const px=p=>x0+(x1-x0)*p/100;
      g.fillStyle='rgba(133,173,209,0.12)'; g.fillRect(px(0),y-5,px(100)-px(0),10);
      g.fillStyle='rgba(49,133,255,0.22)'; g.fillRect(px(25),y-5,px(95)-px(25),10);
      g.strokeStyle='rgba(230,240,248,0.45)'; g.lineWidth=1;
      g.beginPath(); g.moveTo(px(50),y-7); g.lineTo(px(50),y+7); g.stroke();
      const col=it.pct>=95?PAL.red:it.pct>=80?PAL.amber:PAL.green;
      g.beginPath(); g.arc(px(it.pct),y,this.hi===i?5.4:4.2,0,7); g.fillStyle=col; g.fill();
      g.strokeStyle='#080D12'; g.lineWidth=1; g.stroke();
      if(valW){ g.fillStyle=col; g.textAlign='left'; g.font='10px '+MONO; g.fillText('p'+it.pct,x1+5,y); } });
    g.textAlign='center'; g.fillStyle=PAL.mut; g.font='9px '+SANS;
    ['p0','p50','p95'].forEach((t,i)=>{ const p=[0,50,95][i]; g.fillText(t,x0+(x1-x0)*p/100,this.geo.y1+2); });
    g.font='10px '+SANS;
  }
  dDonut(g,w,h,s){
    const cx=w/2,cy=h/2,R=Math.min(w,h)/2-6,r=R*0.62; this.geo={cx,cy,R,r};
    const tot=s.items.reduce((p,c)=>p+c.value,0)||1; let a=-Math.PI/2;
    s.items.forEach((it,i)=>{ const a2=a+it.value/tot*Math.PI*2; const col=it.color||SC[i%6];
      g.beginPath(); g.arc(cx,cy,this.hi===i?R:R-2,a+0.008,a2-0.008); g.arc(cx,cy,r,a2-0.008,a+0.008,true); g.closePath();
      g.fillStyle=this.hi===i?col:col+'D9'; g.fill(); a=a2; });
    g.fillStyle='#E6EDF3'; g.textAlign='center'; g.font='600 15px '+MONO; g.fillText(s.center||fmt(tot),cx,cy-6);
    g.fillStyle=PAL.mut; g.font='9px '+SANS; g.fillText(s.centerSub||'',cx,cy+9);
  }
  dHeat(g,w,h,s){
    const x0=34,y0=4,x1=w-4,y1=h-16; const cw=(x1-x0)/s.cols.length,ch=(y1-y0)/s.rows.length;
    this.geo={x0,y0,cw,ch}; const maxV=Math.max(...s.data.flat())||1;
    s.rows.forEach((rl,r)=>{ g.fillStyle=PAL.mut; g.textAlign='right'; g.font='9.5px '+SANS; g.fillText(rl,x0-5,y0+ch*r+ch/2);
      s.cols.forEach((cl,c)=>{ const v=s.data[r][c]/maxV;
        g.fillStyle='rgba(18,214,197,'+(0.04+v*0.8)+')';
        if(v>0.8) g.fillStyle='rgba(245,165,36,'+v+')'; if(v>0.93) g.fillStyle='rgba(255,77,97,0.95)';
        g.fillRect(x0+cw*c+0.5,y0+ch*r+0.5,cw-1,ch-1);
        if(this.hi===r*s.cols.length+c){ g.strokeStyle='#E6EDF3'; g.lineWidth=1.4; g.strokeRect(x0+cw*c+0.5,y0+ch*r+0.5,cw-1,ch-1); } }); });
    g.textAlign='center'; g.fillStyle=PAL.mut;
    s.cols.forEach((cl,c)=>{ if(c%Math.ceil(s.cols.length/12)===0) g.fillText(cl,x0+cw*c+cw/2,y1+8); });
    g.font='10px '+SANS;
  }
  dSankey(g,w,h,s){
    const cols=[...new Set(s.nodes.map(n=>n.col))].sort((a,b)=>a-b); const nw=10; const colX={};
    cols.forEach((c,i)=>colX[c]=14+(w-120-14)*(i/(cols.length-1||1)));
    const inV={},outV={}; s.nodes.forEach(n=>{inV[n.id]=0;outV[n.id]=0;});
    s.links.forEach(l=>{ outV[l.s]+=l.v; inV[l.t]+=l.v; });
    const nodeV={}; s.nodes.forEach(n=>nodeV[n.id]=Math.max(inV[n.id],outV[n.id]));
    const colSum={}; cols.forEach(c=>colSum[c]=s.nodes.filter(n=>n.col===c).reduce((p,n)=>p+nodeV[n.id],0));
    const scale=(h-30)/(Math.max(...Object.values(colSum))||1)*0.82;
    const geoNodes=[];
    cols.forEach(c=>{ const list=s.nodes.filter(n=>n.col===c);
      const totH=list.reduce((p,n)=>p+nodeV[n.id]*scale,0)+(list.length-1)*10; let y=(h-totH)/2;
      list.forEach(n=>{ const nh=Math.max(4,nodeV[n.id]*scale); n._x=colX[c]; n._y=y; n._h=nh;
        geoNodes.push({x:n._x,y:n._y,w:nw,h:nh,name:n.name,total:nodeV[n.id]}); y+=nh+10; }); });
    this.geo={nodes:geoNodes};
    const oA={},iA={};
    s.links.forEach(l=>{ const a=s.nodes.find(n=>n.id===l.s),b=s.nodes.find(n=>n.id===l.t);
      const lh=Math.max(1.5,l.v*scale);
      const sy=a._y+(oA[l.s]||0)+lh/2; oA[l.s]=(oA[l.s]||0)+lh;
      const ty=b._y+(iA[l.t]||0)+lh/2; iA[l.t]=(iA[l.t]||0)+lh;
      const xa=a._x+nw,xb=b._x,mx=(xa+xb)/2;
      g.beginPath(); g.moveTo(xa,sy); g.bezierCurveTo(mx,sy,mx,ty,xb,ty);
      g.strokeStyle=l.color||(l.risk?'rgba(255,77,97,0.42)':'rgba(49,133,255,0.25)'); g.lineWidth=lh; g.stroke(); });
    const colGap=cols.length>1?((w-120-14)/(cols.length-1)):w;
    const trunc=(t,m)=>{ if(g.measureText(t).width<=m) return t; while(t.length>1&&g.measureText(t+'…').width>m) t=t.slice(0,-1); return t+'…'; };
    s.nodes.forEach(n=>{ g.fillStyle=n.color||PAL.cyan; g.fillRect(n._x,n._y,nw,n._h);
      g.fillStyle='#E6EDF3'; g.textAlign='left'; g.font='10px '+SANS;
      g.fillText(trunc(n.name,Math.max(34,colGap-24)),n._x+nw+5,n._y+Math.max(6,n._h/2));
      g.fillStyle=PAL.mut; g.font='9px '+MONO; g.fillText(fmt(nodeV[n.id])+(s.unit||''),n._x+nw+5,n._y+Math.max(6,n._h/2)+11); });
    g.font='10px '+SANS;
  }
  dSpark(g,w,h,s){
    const d=s.series[0].data; const maxV=Math.max(...d)*1.1||1,minV=Math.min(...d)*0.9;
    const col=s.series[0].color||PAL.cyan; const n=d.length;
    const pts=d.map((v,i)=>[2+(w-4)*i/(n-1),h-3-(h-8)*(v-minV)/(maxV-minV||1)]);
    g.beginPath(); g.moveTo(pts[0][0],h); pts.forEach(p=>g.lineTo(p[0],p[1])); g.lineTo(pts[n-1][0],h); g.closePath();
    const gr=g.createLinearGradient(0,0,0,h); gr.addColorStop(0,col+'3A'); gr.addColorStop(1,col+'00'); g.fillStyle=gr; g.fill();
    g.beginPath(); pts.forEach((p,i)=>i?g.lineTo(p[0],p[1]):g.moveTo(p[0],p[1])); g.strokeStyle=col; g.lineWidth=1.4; g.stroke();
    g.beginPath(); g.arc(pts[n-1][0],pts[n-1][1],2.4,0,7); g.fillStyle=col; g.fill();
  }
}
customElements.define('fc-chart',FCChart);
})();
