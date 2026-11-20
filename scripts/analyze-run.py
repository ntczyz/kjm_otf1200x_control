# analyze-run.py -- summarise a routeA / hostpid CSV log and write a JSON summary.
# ASCII only output (safe for Windows PowerShell 5.1 capture).
import csv, json, sys, os, statistics

def load(path):
    rows = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if not lines:
        return rows
    header = lines[0].split(',')
    for ln in lines[1:]:
        parts = ln.split(',')
        # repair thousands separators in the first column ("1,198.6" -> "1198.6")
        while len(parts) > len(header):
            parts = [parts[0] + parts[1]] + parts[2:]
        rec = dict(zip(header, parts))
        try:
            rows.append({
                't': float(rec.get('elapsed_s', 0)),
                'pv': float(rec.get('PV_C', 0)),
                'sv': float(rec['SV_C']) if rec.get('SV_C') else (float(rec['target_C']) if rec.get('target_C') else None),
                'mv': float(rec['MV_pct']) if rec.get('MV_pct') else 0.0,
                'st': int(float(rec['status'])) if rec.get('status') else 0,
            })
        except Exception:
            pass
    return rows

def main():
    path = sys.argv[1]
    rows = load(path)
    if not rows:
        print('no data'); return
    pv = [r['pv'] for r in rows]
    mv = [r['mv'] for r in rows]
    sv = [r['sv'] for r in rows if r['sv'] is not None]
    peak = max(pv)
    t_peak = next(r['t'] for r in rows if r['pv'] == peak)
    # find time SV reaches its max (start of hold)
    t_hold = None
    if sv:
        smax = max(sv)
        for r in rows:
            if r['sv'] is not None and r['sv'] >= smax - 0.05:
                t_hold = r['t']; break
    # hold window = after PV first reaches 300 (or after t_hold)
    target = max(sv) if sv else max(pv)
    t_reach = next((r['t'] for r in rows if r['pv'] >= target), None)
    hold = [r for r in rows if t_reach is not None and r['t'] >= max(t_reach, (t_hold or 0)) + 60]
    hold_pv = [r['pv'] for r in hold]
    out = {
        'file': os.path.basename(path),
        'samples': len(rows),
        'duration_s': rows[-1]['t'],
        'target_C': target,
        'peak_PV_C': peak,
        'time_to_peak_s': t_peak,
        'first_reach_target_s': t_reach,
        'overshoot_C': round(peak - target, 3),
        'overshoot_pct': round((peak - target) / target * 100, 3) if target else None,
        'hold_samples': len(hold_pv),
        'hold_mean_C': round(statistics.mean(hold_pv), 3) if hold_pv else None,
        'hold_min_C': round(min(hold_pv), 3) if hold_pv else None,
        'hold_max_C': round(max(hold_pv), 3) if hold_pv else None,
        'hold_std_C': round(statistics.pstdev(hold_pv), 3) if len(hold_pv) > 1 else None,
        'hold_pk_pk_C': round(max(hold_pv) - min(hold_pv), 3) if hold_pv else None,
        'MV_max_pct': max(mv), 'MV_min_pct': min(mv),
        'MV_mean_hold_pct': round(statistics.mean([r['mv'] for r in hold]), 2) if hold else None,
    }
    if sv and t_reach is not None:
        errs = [abs(r['sv'] - r['pv']) for r in rows if r['sv'] is not None and r['t'] <= (t_hold or t_reach)]
        if errs:
            out['ramp_max_track_err_C'] = round(max(errs), 3)
            out['ramp_mean_track_err_C'] = round(statistics.mean(errs), 3)
    print(json.dumps(out, indent=2, ensure_ascii=True))
    outp = os.path.splitext(path)[0] + '-summary.json'
    with open(outp, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print('saved: ' + outp)

main()
