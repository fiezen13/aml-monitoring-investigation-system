/* fc-chart-card — unified chart shell: header, subtitle, toolbar (compare/export/fullscreen/view-data),
   legend with series toggle, loading / empty / error states. Wraps one <fc-chart> child. */
(() => {
if (customElements.get('fc-chart-card')) return;
const MONO='"JetBrains Mono", monospace', SANS='Geist, sans-serif';
const ICON={
  compare:'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 18V8M10 18V5M16 18v-7M4 21h16"/></svg>',
  data:'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
  dl:'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 4v11m0 0l-4-4m4 4l4-4M4 20h16"/></svg>',
  full:'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9V4h5M20 15v5h-5M20 9V4h-5M4 15v5h5"/></svg>',
  close:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'
};
class FCChartCard extends HTMLElement {
  static get observedAttributes(){ return ['title','subtitle','state','height','tools','note']; }
  connectedCallback(){
    if(this._init) return; this._init=true;
    this.style.display='block';
    this._compare=false; this._full=false; this._showData=false; this._hidden={};
    this._build();
    this.ro=new ResizeObserver(()=>{ if(this._roQ) return; this._roQ=requestAnimationFrame(()=>{ this._roQ=null; }); });
    this.ro.observe(this);
    requestAnimationFrame(()=>this._sync());
  }
  attributeChangedCallback(){ if(this._init) this._render(); }
  get chart(){ return this.querySelector('fc-chart'); }
  _build(){
    this.style.cssText+=';background:#0D1C2A;border:1px solid rgba(133,173,209,0.14);border-radius:12px;padding:0;overflow:hidden';
    this.head=document.createElement('div');
    this.head.style.cssText='display:flex;align-items:flex-start;gap:8px;padding:11px 13px 6px;flex-wrap:wrap';
    this.body=document.createElement('div'); this.body.style.cssText='position:relative;padding:0 13px 11px';
    this.legend=document.createElement('div');
    this.legend.style.cssText='display:flex;gap:9px;flex-wrap:wrap;padding:0 13px 9px;font-size:10.5px;color:#91A4B5';
    this.foot=document.createElement('div');
    this.foot.style.cssText='padding:0 13px 10px;font-size:10px;color:#4A5D70;line-height:1.5';
    this.state=document.createElement('div');
    this.state.style.cssText='position:absolute;inset:0;display:none;place-items:center;background:rgba(13,28,42,0.92);z-index:3;border-radius:9px;text-align:center;padding:14px';
    this.slotBox=document.createElement('div'); this.slotBox.style.cssText='position:relative';
    // move existing children (the chart) into slotBox
    [...this.childNodes].forEach(n=>{ if(n!==this.head&&n!==this.body) this.slotBox.appendChild(n); });
    this.body.appendChild(this.slotBox); this.body.appendChild(this.state);
    this.insertBefore(this.head,null); this.appendChild(this.legend); this.appendChild(this.body); this.appendChild(this.foot);
    this._render();
  }
  _btn(key,label,active){
    const b=document.createElement('button'); b.type='button'; b.title=label; b.setAttribute('aria-label',label);
    b.style.cssText='display:flex;align-items:center;gap:4px;background:'+(active?'rgba(18,214,197,0.14)':'transparent')+
      ';border:1px solid '+(active?'rgba(18,214,197,0.45)':'rgba(133,173,209,0.18)')+';color:'+(active?'#12D6C5':'#7E93A6')+
      ';border-radius:6px;padding:3px 7px;font:10.5px '+SANS+';cursor:pointer';
    b.innerHTML=ICON[key]||''; b.onmouseenter=()=>{ if(!active){ b.style.color='#E6F0F8'; b.style.borderColor='rgba(133,173,209,0.4)'; } };
    b.onmouseleave=()=>{ if(!active){ b.style.color='#7E93A6'; b.style.borderColor='rgba(133,173,209,0.18)'; } };
    return b;
  }
  _render(){
    const title=this.getAttribute('title')||'', sub=this.getAttribute('subtitle')||'';
    const tools=(this.getAttribute('tools')||'compare,data,dl,full').split(',').map(s=>s.trim());
    const note=this.getAttribute('note')||'';
    this.head.innerHTML='';
    const tw=document.createElement('div'); tw.style.cssText='flex:1;min-width:0';
    tw.innerHTML='<div style="font-size:12.5px;font-weight:600;color:#E6F0F8;line-height:1.3">'+title+'</div>'+
      (sub?'<div style="font-size:10.5px;color:#607487;margin-top:1px">'+sub+'</div>':'');
    this.head.appendChild(tw);
    const bar=document.createElement('div'); bar.style.cssText='display:flex;gap:4px;flex:none';
    if(tools.includes('compare')){ const b=this._btn('compare','So sánh kỳ trước',this._compare);
      b.onclick=()=>{ this._compare=!this._compare; this._applyCompare(); this._render(); }; bar.appendChild(b); }
    if(tools.includes('data')){ const b=this._btn('data','Xem dữ liệu gốc',this._showData);
      b.onclick=()=>{ this._showData=!this._showData; this._renderData(); this._render(); }; bar.appendChild(b); }
    if(tools.includes('dl')){ const b=this._btn('dl','Tải PNG (mock)',false);
      b.onclick=()=>{ const c=this.chart; if(c&&c.exportPNG) c.exportPNG((title||'chart').replace(/\s+/g,'-'));
        this.dispatchEvent(new CustomEvent('exported',{bubbles:true,detail:{title}})); }; bar.appendChild(b); }
    if(tools.includes('full')){ const b=this._btn('full',this._full?'Thoát fullscreen':'Fullscreen',this._full);
      b.onclick=()=>this.toggleFull(); bar.appendChild(b); }
    this.head.appendChild(bar);
    this.foot.textContent=note; this.foot.style.display=note?'block':'none';
    this._sync();
  }
  _applyCompare(){
    const c=this.chart; if(!c||!c.data) return;
    const s=c.data;
    if(this._compare){ if(!s._cmp&&s.series&&s.labels){
        s._cmp=true; s.compare={series:s.series.slice(0,2).map(se=>({name:se.name+' (kỳ trước)',
          data:se.data.map((v,i)=>Math.max(0,v*(0.72+((i*37)%23)/60)))}))}; } }
    else { s.compare=null; s._cmp=false; }
    c.data=s;
  }
  _renderData(){
    if(this._dataBox){ this._dataBox.remove(); this._dataBox=null; }
    if(!this._showData) return;
    const c=this.chart; const td=c&&c.tableData; if(!td||!td.cols.length) return;
    const box=document.createElement('div');
    box.style.cssText='margin-top:8px;max-height:150px;overflow:auto;border:1px solid rgba(133,173,209,0.14);border-radius:8px;background:#0A1724';
    let html='<table style="width:100%;border-collapse:collapse;font:10.5px '+MONO+'"><thead><tr>'+
      td.cols.map(c2=>'<th style="text-align:left;padding:5px 8px;color:#607487;font-weight:500;position:sticky;top:0;background:#0A1724;border-bottom:1px solid rgba(133,173,209,0.14);white-space:nowrap">'+c2+'</th>').join('')+'</tr></thead><tbody>';
    td.rows.slice(0,60).forEach(r=>{ html+='<tr>'+r.map((v,i)=>'<td style="padding:4px 8px;color:'+(i?'#D4E3EE':'#91A4B5')+';border-bottom:1px solid rgba(133,173,209,0.05);white-space:nowrap;font-variant-numeric:tabular-nums">'+v+'</td>').join('')+'</tr>'; });
    html+='</tbody></table>';
    box.innerHTML=html; this._dataBox=box; this.body.appendChild(box);
  }
  _sync(){
    const st=this.getAttribute('state')||'ok';
    const c=this.chart; const hh=this.getAttribute('height');
    if(c&&hh) c.style.height=hh;
    // legend
    this.legend.innerHTML='';
    const items=(c&&c.legend)||[];
    if(items.length>1&&st==='ok'){
      items.forEach((it,i)=>{
        const off=!!this._hidden[i];
        const el=document.createElement('button'); el.type='button';
        el.style.cssText='display:flex;align-items:center;gap:5px;background:none;border:none;padding:0;cursor:pointer;font:10.5px '+SANS+';color:'+(off?'#4A5D70':'#91A4B5');
        el.innerHTML='<span style="width:8px;height:8px;border-radius:2px;background:'+(off?'#33465A':it.color)+';display:inline-block"></span>'+it.name;
        el.onclick=()=>{ this._hidden[i]=!off; const s=c.data;
          if(s&&s.series){ s.series.forEach((se,k)=>{ se.hidden=!!this._hidden[k]; }); c.data=s; }
          this._sync(); };
        this.legend.appendChild(el); });
      this.legend.style.display='flex';
    } else this.legend.style.display='none';
    // state overlay
    if(st==='ok'){ this.state.style.display='none'; if(c) c.style.visibility='visible'; }
    else { this.state.style.display='grid'; if(c) c.style.visibility='hidden';
      if(st==='loading') this.state.innerHTML='<div><div style="width:26px;height:26px;margin:0 auto 8px;border-radius:50%;border:2px solid rgba(18,214,197,0.15);border-top-color:#12D6C5;animation:fcSpin .9s linear infinite"></div><span style="font:11px '+SANS+';color:#607487">Đang tải dữ liệu…</span></div><style>@keyframes fcSpin{to{transform:rotate(360deg)}}</style>';
      else if(st==='empty') this.state.innerHTML='<div style="font:11.5px '+SANS+';color:#607487;line-height:1.6"><div style="font-size:18px;color:#33465A;margin-bottom:4px">◌</div>Không có dữ liệu trong khoảng đã chọn<br><span style="font-size:10.5px;color:#4A5D70">Thử mở rộng cửa sổ thời gian hoặc bỏ bớt filter</span></div>';
      else this.state.innerHTML='<div style="font:11.5px '+SANS+';color:#FF6B7C;line-height:1.6"><div style="font-size:18px;margin-bottom:4px">⚠</div>Không tải được dữ liệu chart<br><span style="font-size:10.5px;color:#91A4B5">Pipeline nguồn đang trễ — thử lại sau</span></div>'; }
  }
  toggleFull(){
    this._full=!this._full;
    if(this._full){
      this._prev={pos:this.style.position,z:this.style.zIndex,inset:this.style.inset,w:this.style.width,h:this.style.height};
      this.style.position='fixed'; this.style.inset='24px'; this.style.zIndex='90';
      this.style.width='auto'; this.style.height='auto'; this.style.boxShadow='0 30px 90px rgba(0,0,0,0.65)';
      const c=this.chart; if(c){ this._prevH=c.style.height; c.style.height='calc(100vh - 190px)'; }
      if(!this._esc){ this._esc=(e)=>{ if(e.key==='Escape'&&this._full) this.toggleFull(); }; window.addEventListener('keydown',this._esc); }
    } else {
      const p=this._prev||{}; this.style.position=p.pos||''; this.style.inset=p.inset||''; this.style.zIndex=p.z||'';
      this.style.width=p.w||''; this.style.height=p.h||''; this.style.boxShadow='';
      const c=this.chart; if(c) c.style.height=this._prevH||this.getAttribute('height')||'';
    }
    this._render();
  }
}
customElements.define('fc-chart-card',FCChartCard);
})();
