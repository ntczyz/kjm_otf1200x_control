# compare-cooling.py -- publication-style (Origin-like) cooling-curve comparison.
#   Large Arial fonts, round temperature ticks, inward ticks, full frame, boxed legend, 2 panels.
# usage: compare-cooling.py <out.png> <csv1> <label1> <csv2> <label2> ...
import csv, os, sys, math
from PIL import Image, ImageDraw, ImageFont

ARIAL = 'C:/Windows/Fonts/arial.ttf'
ARIALB = 'C:/Windows/Fonts/arialbd.ttf'
def F(sz, bold=False):
    try:
        return ImageFont.truetype(ARIALB if bold else ARIAL, sz)
    except Exception:
        return ImageFont.load_default()

COLORS = ['#c0392b', '#2471a3', '#1e8449', '#7d3c98', '#b9770e']

def draw_vtext(img, xy, text, font, fill='black'):
    """rotated 90 deg text (Origin-style vertical axis title), centred at xy"""
    tmp = Image.new('RGBA', (1, 1))
    td = ImageDraw.Draw(tmp)
    bb = td.textbbox((0, 0), text, font=font)
    w = bb[2] - bb[0] + 12
    h = bb[3] - bb[1] + 12
    tmp = Image.new('RGBA', (w, h), (255, 255, 255, 0))
    td = ImageDraw.Draw(tmp)
    td.text((6 - bb[0], 6 - bb[1]), text, font=font, fill=fill)
    rot = tmp.rotate(90, expand=True)
    img.paste(rot, (int(xy[0] - rot.width / 2), int(xy[1] - rot.height / 2)), rot)

def load_cool(path):
    rows = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            try:
                if r.get('phase') != 'cool':
                    continue
                rows.append((float(r['elapsed_s']), float(r['PV_C'])))
            except Exception:
                pass
    if not rows:
        return []
    t0 = rows[0][0]
    return [(t - t0, pv) for t, pv in rows]

def rate_vs_T(rows, win=20.0):
    out = []
    i = 0
    n = len(rows)
    while i < n:
        j = i
        while j + 1 < n and rows[j + 1][0] - rows[i][0] < win:
            j += 1
        dt = rows[j][0] - rows[i][0]
        if dt > 1:
            out.append((rows[i][1], (rows[i][1] - rows[j][1]) / dt * 60.0))
        i += 5
    return out

def main():
    out = sys.argv[1]
    args = sys.argv[2:]
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args) - 1, 2)]

    series = []
    for path, label in pairs:
        rows = load_cool(path)
        if rows:
            t100 = next((t / 60.0 for t, pv in rows if pv <= 101.0), None)
            if t100 is not None:
                label = '%s  (\u2192 100 \u00b0C in %.1f min)' % (label, t100)
            series.append({'label': label, 'rows': rows, 'rate': rate_vs_T(rows)})
    if not series:
        print('no data'); return

    # ---- font sizes (larger) ----
    FS_TICK = 26
    FS_AXIS = 32
    FS_LEG = 25
    FS_PANEL = 36

    W, H = 2000, 1560
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)

    # ================= panel (a): T vs t =================
    ax0, ax1 = 210, W - 70
    ay0, ay1 = 100, 830
    tmax = max(s['rows'][-1][0] for s in series) / 60.0
    tspan = max(30, math.ceil(tmax / 10.0) * 10)
    YMIN, YMAX = 0.0, 700.0          # round limits
    YSTEP = 100.0                    # round ticks
    def AX(t): return ax0 + (t / tspan) * (ax1 - ax0)
    def AY(v): return ay1 - (v - YMIN) / (YMAX - YMIN) * (ay1 - ay0)

    # grid
    v = YMIN
    while v <= YMAX + 1e-6:
        y = AY(v)
        d.line([ax0, y, ax1, y], fill='#d9d9d9')
        v += YSTEP
    # round time step
    tstep = 20 if tspan <= 120 else (30 if tspan <= 180 else 60)
    tt = 0
    while tt <= tspan + 1e-6:
        x = AX(tt)
        d.line([x, ay0, x, ay1], fill='#d9d9d9')
        tt += tstep
    # curves
    for k, s in enumerate(series):
        pts = [(AX(t / 60.0), AY(pv)) for t, pv in s['rows']]
        d.line(pts, fill=COLORS[k % len(COLORS)], width=5)
    # frame
    d.rectangle([ax0, ay0, ax1, ay1], outline='black', width=2)
    # ticks (inward, round labels)
    v = YMIN
    while v <= YMAX + 1e-6:
        y = AY(v)
        d.line([ax0, y, ax0 + 16, y], fill='black', width=2)
        d.text((ax0 - 14, y), '%.0f' % v, fill='black', font=F(FS_TICK), anchor='rm')
        v += YSTEP
    tt = 0
    while tt <= tspan + 1e-6:
        x = AX(tt)
        d.line([x, ay1, x, ay1 - 16], fill='black', width=2)
        d.text((x, ay1 + 16), '%.0f' % tt, fill='black', font=F(FS_TICK), anchor='ma')
        tt += tstep
    d.text(((ax0 + ax1) / 2, ay1 + 62), 'Time (min)', fill='black', font=F(FS_AXIS, True), anchor='ma')
    draw_vtext(img, (78, (ay0 + ay1) / 2), 'Temperature (\u00b0C)', F(FS_AXIS, True))
    d.text((ax0 + 12, ay0 + 12), '(a)', fill='black', font=F(FS_PANEL, True))

    # legend (boxed, top right)
    lx = ax1 - 830
    ly = ay0 + 30
    lh = 44 * len(series) + 26
    d.rectangle([lx, ly, ax1 - 30, ly + lh], outline='black', width=2)
    for k, s in enumerate(series):
        yy = ly + 26 + 44 * k
        d.line([lx + 20, yy, lx + 100, yy], fill=COLORS[k % len(COLORS)], width=5)
        d.text((lx + 116, yy), s['label'], fill='black', font=F(FS_LEG), anchor='lm')

    # ================= panel (b): cooling rate vs T =================
    bx0, bx1 = 210, W - 70
    by0, by1 = 1030, 1420
    TMIN, TMAX = 0.0, 700.0          # round limits (cooling right -> left)
    def BX(T): return bx0 + ((TMAX - T) / (TMAX - TMIN)) * (bx1 - bx0)
    rmax = 160.0
    rst = 40.0
    def BY(v): return by1 - (min(rmax, max(0, v)) / rmax) * (by1 - by0)
    for i in range(0, 5):
        vv = rmax * i / 4
        y = BY(vv)
        d.line([bx0, y, bx1, y], fill='#d9d9d9')
    for i in range(0, 8):
        T = TMIN + (TMAX - TMIN) * i / 7
        x = BX(T)
        d.line([x, by0, x, by1], fill='#d9d9d9')
    for k, s in enumerate(series):
        pts = [(BX(T), BY(rt)) for (T, rt) in s['rate'] if 100 <= T <= 700]
        if len(pts) > 1:
            d.line(pts, fill=COLORS[k % len(COLORS)], width=4)
    d.rectangle([bx0, by0, bx1, by1], outline='black', width=2)
    vv = 0.0
    while vv <= rmax + 1e-6:
        y = BY(vv)
        d.line([bx0, y, bx0 + 16, y], fill='black', width=2)
        d.text((bx0 - 14, y), '%.0f' % vv, fill='black', font=F(FS_TICK), anchor='rm')
        vv += rst
    for T in range(700, 0, -100):
        x = BX(T)
        d.line([x, by1, x, by1 - 16], fill='black', width=2)
        d.text((x, by1 + 16), '%.0f' % T, fill='black', font=F(FS_TICK), anchor='ma')
    d.text(((bx0 + bx1) / 2, by1 + 62), 'Temperature (\u00b0C)', fill='black', font=F(FS_AXIS, True), anchor='ma')
    draw_vtext(img, (78, (by0 + by1) / 2), 'Cooling rate (\u00b0C/min)', F(FS_AXIS, True))
    d.text((bx0 + 12, by0 + 12), '(b)', fill='black', font=F(FS_PANEL, True))

    img.save(out)
    print('saved: ' + out)

main()
