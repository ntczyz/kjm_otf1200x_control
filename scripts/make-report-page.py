# make-report-page.py -- interactive (hover crosshair + tooltip) HTML report for a run CSV.
#   usage: make-report-page.py <csv> <out.html> [title]
# The page embeds the data as JSON and draws the charts on <canvas>, with a shared
# mouse-follow crosshair and a tooltip showing time / PV / SV / MV.
import csv, os, sys, json, html, math
import numpy as np

def load(path):
    rows = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) < 2:
        return rows
    header = lines[0].split(',')
    for ln in lines[1:]:
        parts = ln.split(',')
        while len(parts) > len(header):
            parts = [parts[0] + parts[1]] + parts[2:]
        r = dict(zip(header, parts))
        try:
            rows.append({
                't': float(r.get('elapsed_s', 0)),
                'pv': float(r.get('PV_C', 0)),
                'sv': float(r['SV_C']) if r.get('SV_C') else (float(r['target_C']) if r.get('target_C') else None),
                'mv': float(r.get('MV_pct', 0)) if r.get('MV_pct') else 0.0,
                'ph': r.get('phase', ''),
            })
        except Exception:
            pass
    return rows

def stats(rows):
    out = {}
    if not rows:
        return out
    out['samples'] = len(rows)
    out['duration_min'] = round(rows[-1]['t'] / 60.0, 1)
    pv = [r['pv'] for r in rows]
    out['pv_max'] = round(max(pv), 1)
    # time to first reach 700 (or max target)
    tgt = 700.0
    hit = next((r['t'] for r in rows if r['pv'] >= tgt - 2), None)
    out['t_reach_min'] = round(hit / 60.0, 1) if hit else None
    hold = [r for r in rows if r['ph'] == 'hold']
    if hold:
        h = [r['pv'] for r in hold]
        out['hold_avg'] = round(sum(h) / len(h), 2)
        out['hold_min'] = round(min(h), 2)
        out['hold_max'] = round(max(h), 2)
        out['hold_minutes'] = round((hold[-1]['t'] - hold[0]['t']) / 60.0, 1)
    cool = [r for r in rows if r['ph'] == 'cool']
    if cool:
        out['cool_minutes'] = round((cool[-1]['t'] - cool[0]['t']) / 60.0, 1)
        out['cool_start'] = round(cool[0]['pv'], 1)
        out['cool_end'] = round(cool[-1]['pv'], 1)
    return out

def fit_segment_two(t, pv):
    """grid search tau1, tau2, Tamb; linear LSQ for A1,A2 -> (dict or None)"""
    t = np.asarray(t, dtype=float); pv = np.asarray(pv, dtype=float)
    t0 = t[0]; x = t - t0
    best = None
    for tamb in np.arange(18.0, 33.0, 1.0):
        y = pv - tamb
        if (y <= 0).any():
            continue
        for tau1 in np.arange(0.3, 6.0, 0.3):
            e1 = np.exp(-x / (tau1 * 60.0))
            for tau2 in np.arange(4.0, 120.0, 2.0):
                if tau2 <= tau1 * 1.6:
                    continue
                e2 = np.exp(-x / (tau2 * 60.0))
                A = np.vstack([e1, e2]).T
                try:
                    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
                except Exception:
                    continue
                pred = A @ coef
                ss_res = float(((y - pred) ** 2).sum())
                if best is None or ss_res < best['ss_res']:
                    best = {'tamb': float(tamb), 'tau1': float(tau1), 'tau2': float(tau2),
                            'a1': float(coef[0]), 'a2': float(coef[1]),
                            'ss_res': ss_res, 't0': float(t0),
                            't1': float(t[-1]), 'n': int(len(pv))}
    if best is None:
        return None
    ss_tot = float(((pv - pv.mean()) ** 2).sum())
    best['r2'] = 1 - best['ss_res'] / ss_tot if ss_tot > 0 else 0
    best['rmse'] = math.sqrt(best['ss_res'] / len(pv))
    return best

def build_fits(rows, events):
    """split the cooling phase at the event times and fit each part"""
    cool = [r for r in rows if r.get('ph') == 'cool']
    if len(cool) < 60:
        return []
    evs = sorted([e[0] for e in events]) if events else []
    bounds = [cool[0]['t']] + [e for e in evs if cool[0]['t'] < e < cool[-1]['t']] + [cool[-1]['t']]
    fits = []
    for i in range(len(bounds) - 1):
        seg = [r for r in cool if bounds[i] <= r['t'] <= bounds[i + 1]]
        if len(seg) < 40:
            continue
        r = fit_segment_two([s['t'] for s in seg], [s['pv'] for s in seg])
        if r:
            r['seg'] = i + 1
            fits.append(r)
    return fits

def main():
    src, out = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(src)
    events = []
    for a in sys.argv[4:]:
        if a.startswith('--events='):
            for part in a[len('--events='):].split(';'):
                if ':' in part:
                    t, lab = part.split(':', 1)
                    try:
                        events.append([float(t), lab])
                    except Exception:
                        pass
    rows = load(src)
    st = stats(rows)
    live = '--live' in sys.argv
    # the grid-search fit is slow (~3 s) -> only compute it for the final static report
    fits = [] if live else build_fits(rows, events)
    live_js = ''
    if live:
        live_js = """
let reloadTimer=null;
function scheduleReload(){ if(reloadTimer) clearTimeout(reloadTimer); reloadTimer=setTimeout(()=>location.reload(), 5000); }
function pauseReload(){ if(reloadTimer){ clearTimeout(reloadTimer); reloadTimer=null; } }
for(const c of [c1,c2]){ c.addEventListener('mouseenter', pauseReload); c.addEventListener('mouseleave', scheduleReload); }
scheduleReload();
"""
    data = [[round(r['t'], 1), round(r['pv'], 1), (round(r['sv'], 1) if r['sv'] is not None else None), round(r['mv'], 0), r['ph']] for r in rows]
    payload = json.dumps(data, separators=(',', ':'))
    st_html = ''.join(
        '<div class="card"><div class="k">%s</div><div class="v">%s</div></div>' % (k, v)
        for k, v in [
            ('samples', st.get('samples', 0)),
            ('duration', '%.1f min' % st.get('duration_min', 0)),
            ('ramp to 700C', ('%.1f min' % st['t_reach_min']) if st.get('t_reach_min') else '-'),
            ('hold avg', ('%.2f C' % st['hold_avg']) if 'hold_avg' in st else '-'),
            ('hold range', ('%.2f ~ %.2f C' % (st['hold_min'], st['hold_max'])) if 'hold_min' in st else '-'),
            ('max PV', '%.1f C' % st.get('pv_max', 0)),
            ('cooling time', ('%.1f min' % st['cool_minutes']) if 'cool_minutes' in st else '-'),
            ('peak MV', '100 %'),
        ])
    page = """<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
 body{margin:0;background:#0d1117;color:#c9d1d9;font-family:Segoe UI,Arial,sans-serif}
 .wrap{padding:18px 24px;max-width:1300px}
 h1{font-size:20px;margin:0 0 4px}
 .sub{color:#8b949e;font-size:13px;margin-bottom:14px}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
 .card{flex:1;min-width:130px;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px}
 .card .k{color:#8b949e;font-size:12px}
 .card .v{font-size:22px;font-weight:700;color:#58a6ff}
 .box{position:relative;margin-bottom:14px}
 canvas{display:block;width:100%;background:#0d1117;border:1px solid #30363d;border-radius:8px;cursor:crosshair}
 #tip{position:absolute;pointer-events:none;background:#161b22ee;border:1px solid #58a6ff;border-radius:6px;
      padding:6px 10px;font-size:13px;line-height:1.5;display:none;white-space:nowrap;z-index:5}
 .hint{color:#484f58;font-size:12px;margin-top:10px}
</style></head><body><div class="wrap">
<h1>__TITLE__</h1>
<div class="sub">hover the chart to inspect time / temperature / output</div>
<div class="cards">__CARDS__</div>
<div class="box"><canvas id="c1" height="420"></canvas><div id="tip"></div></div>
<div class="box"><canvas id="c2" height="170"></canvas></div>
<div class="hint">red = PV, dashed blue = SV, green = MV output, <b style="color:#f0f6fc">thin white = two-exponential cooling fit</b> (hover to see fit value / residual / segment tau) &nbsp;|&nbsp; source: __SRC__</div>
</div>
<script>
const D = __DATA__;
const EV = __EVENTS__;
const FITS = __FITS__;
function fitAt(t){
  for(const f of FITS){ if(t>=f.t0 && t<=f.t1){
    const v = f.tamb + f.a1*Math.exp(-(t-f.t0)/(f.tau1*60)) + f.a2*Math.exp(-(t-f.t0)/(f.tau2*60));
    return {v:v, f:f};
  } }
  return null;
}
const c1 = document.getElementById('c1'), c2 = document.getElementById('c2');
const tip = document.getElementById('tip');
const ctx1 = c1.getContext('2d'), ctx2 = c2.getContext('2d');
let W=0, H=0, W2=0, H2=0;
const PADL=62, PADR=18, PADT=18, PADB=40;
const TMAX = D.length ? D[D.length-1][0] : 1;
const SPAN = niceSpan(TMAX);
let YMIN=0, YMAX=1;
function niceSpan(v){ const S=[30,60,120,180,300,600,900,1200,1800,2700,3600,5400,7200,10800,14400,21600,28800];
  for(const s of S){ if(v<=s) return s; } return v*1.2; }
function fmt(sec){ sec=Math.round(sec); const m=Math.floor(sec/60), s=sec%60; return m+':'+String(s).padStart(2,'0'); }
function resize(){
  const r = c1.getBoundingClientRect();
  W = Math.floor(r.width); H = 420; c1.width = W*window.devicePixelRatio; c1.height = H*window.devicePixelRatio;
  ctx1.setTransform(window.devicePixelRatio,0,0,window.devicePixelRatio,0,0);
  const r2 = c2.getBoundingClientRect();
  W2 = Math.floor(r2.width); H2 = 170; c2.width = W2*window.devicePixelRatio; c2.height = H2*window.devicePixelRatio;
  ctx2.setTransform(window.devicePixelRatio,0,0,window.devicePixelRatio,0,0);
  computeY(); draw(null);
}
function computeY(){
  let lo=1e9, hi=-1e9;
  for(const d of D){ lo=Math.min(lo,d[1]); hi=Math.max(hi,d[1]); if(d[2]!=null){lo=Math.min(lo,d[2]); hi=Math.max(hi,d[2]);} }
  if(lo>hi){ lo=0; hi=100; }
  const pad=(hi-lo)*0.08+5;
  YMIN=Math.max(0, Math.floor((lo-pad)/10)*10); YMAX=Math.ceil((hi+pad)/10)*10;
}
function X(t){ return PADL + (t/SPAN)*(W-PADL-PADR); }
function Y(v){ return H-PADB - (v-YMIN)/(YMAX-YMIN)*(H-PADT-PADB); }
function X2(t){ return PADL + (t/SPAN)*(W2-PADL-PADR); }
function Y2(v){ return H2-30 - Math.min(100,Math.max(0,v))/100*(H2-16-30); }
function draw(hoverIdx){
  ctx1.clearRect(0,0,W,H);
  ctx2.clearRect(0,0,W2,H2);
  // y grid
  const ystep = niceStep((YMAX-YMIN)/5);
  ctx1.font='12px Segoe UI'; ctx1.fillStyle='#8b949e'; ctx1.textAlign='right';
  for(let v=YMIN; v<=YMAX+1e-6; v+=ystep){
    const y=Y(v); ctx1.strokeStyle='#21262d'; ctx1.beginPath(); ctx1.moveTo(PADL,y); ctx1.lineTo(W-PADR,y); ctx1.stroke();
    ctx1.fillText(Math.round(v), PADL-8, y+4);
  }
  // x grid
  ctx1.textAlign='center';
  for(let i=0;i<=6;i++){ const t=SPAN*i/6, x=X(t);
    ctx1.strokeStyle='#21262d'; ctx1.beginPath(); ctx1.moveTo(x,PADT); ctx1.lineTo(x,H-PADB); ctx1.stroke();
    ctx2.strokeStyle='#21262d'; ctx2.beginPath(); ctx2.moveTo(X2(t),16); ctx2.lineTo(X2(t),H2-30); ctx2.stroke();
    ctx1.fillText(fmt(t), x, H-PADB+18);
  }
  // sv
  ctx1.setLineDash([7,5]); ctx1.strokeStyle='#58a6ff'; ctx1.lineWidth=2; ctx1.beginPath();
  let started=false;
  for(const d of D){ if(d[2]==null) continue; const x=X(d[0]), y=Y(d[2]); if(!started){ctx1.moveTo(x,y);started=true;} else ctx1.lineTo(x,y); }
  ctx1.stroke(); ctx1.setLineDash([]);
  // pv
  ctx1.strokeStyle='#f85149'; ctx1.lineWidth=2.5; ctx1.beginPath();
  D.forEach((d,i)=>{ const x=X(d[0]), y=Y(d[1]); i?ctx1.lineTo(x,y):ctx1.moveTo(x,y); });
  ctx1.stroke();
  // mv
  ctx2.strokeStyle='#3fb950'; ctx2.lineWidth=2; ctx2.beginPath();
  D.forEach((d,i)=>{ const x=X2(d[0]), y=Y2(d[3]); i?ctx2.lineTo(x,y):ctx2.moveTo(x,y); });
  ctx2.stroke();
  // two-exponential fitted curves (cooling phase)
  ctx1.strokeStyle='#f0f6fc'; ctx1.lineWidth=1.6;
  for(const f of FITS){
    let started=false; ctx1.beginPath();
    for(const d of D){
      if(d[0]<f.t0 || d[0]>f.t1) continue;
      const v=f.tamb+f.a1*Math.exp(-(d[0]-f.t0)/(f.tau1*60))+f.a2*Math.exp(-(d[0]-f.t0)/(f.tau2*60));
      const x=X(d[0]), y=Y(v);
      if(!started){ctx1.moveTo(x,y);started=true;} else ctx1.lineTo(x,y);
    }
    ctx1.stroke();
  }
  ctx2.fillStyle='#8b949e'; ctx2.textAlign='right';
  for(const v of [0,50,100]){ const y=Y2(v); ctx2.strokeStyle='#21262d'; ctx2.beginPath(); ctx2.moveTo(PADL,y); ctx2.lineTo(W2-PADR,y); ctx2.stroke(); ctx2.fillText(v+'%', PADL-8, y+4); }
  // event markers (e.g. furnace opened)
  ctx1.textAlign='left'; ctx1.font='12px Segoe UI';
  for(const ev of EV){
    const x=X(ev[0]);
    if(x<PADL||x>W-PADR) continue;
    ctx1.strokeStyle='#d29922'; ctx1.setLineDash([4,4]); ctx1.beginPath(); ctx1.moveTo(x,PADT); ctx1.lineTo(x,H-PADB); ctx1.stroke(); ctx1.setLineDash([]);
    ctx1.fillStyle='#d29922'; ctx1.fillText(ev[1], x+4, PADT+14);
    ctx2.strokeStyle='#d29922'; ctx2.setLineDash([4,4]); ctx2.beginPath(); ctx2.moveTo(X2(ev[0]),16); ctx2.lineTo(X2(ev[0]),H2-30); ctx2.stroke(); ctx2.setLineDash([]);
  }
  if(hoverIdx!=null && hoverIdx>=0 && hoverIdx<D.length){
    const d=D[hoverIdx];
    const x=X(d[0]), x2=X2(d[0]);
    ctx1.strokeStyle='#8b949e'; ctx1.setLineDash([3,3]); ctx1.beginPath(); ctx1.moveTo(x,PADT); ctx1.lineTo(x,H-PADB); ctx1.stroke(); ctx1.setLineDash([]);
    ctx1.fillStyle='#f85149'; ctx1.beginPath(); ctx1.arc(x,Y(d[1]),4,0,7); ctx1.fill();
    ctx2.strokeStyle='#8b949e'; ctx2.setLineDash([3,3]); ctx2.beginPath(); ctx2.moveTo(x2,16); ctx2.lineTo(x2,H2-30); ctx2.stroke(); ctx2.setLineDash([]);
    const pv=d[1].toFixed(1), sv=(d[2]!=null?d[2].toFixed(1):'-'), mv=d[3].toFixed(0);
    let fitTxt='';
    const fa=fitAt(d[0]);
    if(fa){
      const e=d[1]-fa.v;
      fitTxt='<br><span style="color:#8b949e">fit <b style="color:#f0f6fc">'+fa.v.toFixed(1)+' C</b> (err '+(e>=0?'+':'')+e.toFixed(1)+')'
            +'<br>seg'+fa.f.seg+'  tau1='+fa.f.tau1.toFixed(2)+'  tau2='+fa.f.tau2.toFixed(1)+' min  R2='+fa.f.r2.toFixed(4)+'</span>';
    }
    tip.innerHTML='time <b>'+fmt(d[0])+'</b><br>PV <b style="color:#f85149">'+pv+' C</b><br>SV <b style="color:#58a6ff">'+sv+' C</b><br>MV <b style="color:#3fb950">'+mv+'%</b>'+fitTxt;
    tip.style.display='block';
    const bx = x + 14, by = Math.max(4, Y(d[1]) - 70);
    tip.style.left = Math.min(W-170, bx) + 'px';
    tip.style.top = by + 'px';
  } else { tip.style.display='none'; }
}
function niceStep(v){ for(const s of [1,2,5,10,20,25,50,100,200,250,500,1000]){ if(v<=s) return s; } return 2000; }
function idxFromX(px){
  if(!D.length) return null;
  const t = (px - PADL)/(W-PADL-PADR)*SPAN;
  let lo=0, hi=D.length-1;
  while(lo<hi){ const mid=(lo+hi)>>1; if(D[mid][0]<t) lo=mid+1; else hi=mid; }
  if(lo>0 && Math.abs(D[lo-1][0]-t) < Math.abs(D[lo][0]-t)) lo=lo-1;
  return lo;
}
c1.addEventListener('mousemove', e=>{ const r=c1.getBoundingClientRect(); draw(idxFromX(e.clientX-r.left)); });
c2.addEventListener('mousemove', e=>{ const r=c2.getBoundingClientRect(); draw(idxFromX(e.clientX-r.left)); });
c1.addEventListener('mouseleave', ()=>draw(null));
c2.addEventListener('mouseleave', ()=>draw(null));
window.addEventListener('resize', resize);
resize();
__LIVE__
</script></body></html>"""
    page = (page.replace('__TITLE__', html.escape(title))
                .replace('__CARDS__', st_html)
                .replace('__SRC__', html.escape(os.path.basename(src)))
                .replace('__EVENTS__', json.dumps(events))
                .replace('__FITS__', json.dumps(fits))
                .replace('__LIVE__', live_js)
                .replace('__DATA__', payload))
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print('wrote ' + out + '  rows=' + str(len(data)))

main()
