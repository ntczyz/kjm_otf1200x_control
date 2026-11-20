# AI-858 parameters that matter

## Model code

```
AI-858  A   N   X3   L3   N   S2
        │   │   │    │    │   └── ⑥ output module: S2 (SSR / linear voltage)
        │   │   │    │    └────── ⑤ AUX: N = none (no cooling/aux output)
        │   │   │    └─────────── ④ ALM: L3 (dual relay)
        │   │   └──────────────── ③ OUTP: X3 (triac/SSR drive)
        │   └──────────────────── ② main output: N (none)
        └──────────────────────── ① size: A = 96×96 mm
```

## AFC — auxiliary function code

`AFC = A×1 + D×8 + F×32 + G×64`

| AFC | Meaning |
|---|---|
| 1 | AI bus, **no parity (8N1)** |
| 9 | AI bus, **even parity (8E1)** ← our setup |

Other bits switch the alarm output, the COMM port into 4–20 mA / switch input /
alarm output, etc.

## bAud — **do not change casually**

| bAud | Result |
|---|---|
| 9 | 1200 |
| 0 | 19200 ← our setup |
| 1 | 9600 |
| 2 | 4800 |
| 3 | 2400 |
| **4** | COMM becomes **4–20 mA output** — no comms |
| **8** | COMM becomes **switch input** — no comms |
| **12** | COMM becomes **alarm output** — no comms |

If communication suddenly stops after changing `bAud`, this is why.

## dPt — decimal point

- **Write range 0–3** (0 = no decimal, 1 = 0.0, 2 = 0.00, 3 = 0.000).
- **Read adds +127**: write `0` → read `128`; write `1` → read `1`.
- With `INP=0` (K thermocouple) the communication layer is fixed at one decimal,
  so `PV=216` always means 21.6 °C regardless of `dPt`.
- The original factory state on our unit was `dPt` read = 128 (display without a
  decimal). Writing 1 makes the panel show 0.1 °C.

## SPr — ramp rate (setpoint ramp)

- Unit is **0.1 °C/min**: `SPr = rate × 10`.
- `SPr=450` → 45 °C/min.
- `SPr=27` → 2.7 °C/min (the classic mistake).
- `SPr=0` disables the ramp (setpoint steps).

## OPH / OPL — output limits

- `OPH` percent, e.g. 60 = 60 % max output, 80 = 80 %.
- The instrument clamps the average output, but the `MV` readout can still
  reach 100 — do not confuse the two.

## Srun — run / stop / hold

| Srun | Effect |
|---|---|
| 0 | **run** — and in FSV mode this also forces AUTO |
| 1 | **stop** — output off, state StoP |
| 2 | hold (program paused) |

> `StoP` disables the output even in manual mode. To let MV drive the heater you
> must write `Srun=0`. Writing `AMAn` alone does **not** change manual→auto;
> `Srun=0` does.

## AMAn — control mode

| AMAn | Mode |
|---|---|
| 0 | none / off |
| 1 | manual |
| 2 | FSV (standard PID) ← our setup |
| 3 | on/off |

## Pno — program number

- `Pno=0` — program off (the instrument follows `SV` + `SPr`).
- `Pno=50` — the factory 50-segment program (SP1/t1 … SP50/t50 at 0x50+).
- `PAF=40` — program time unit = minutes.

Our factory program, backed up before experiments:

```
SP1 = 0     t1 = 400   (0 → 400 °C in 40 min)
SP2 = 4000  t2 = 650   (400 → 1050 °C in 65 min)
SP3 = 10500 t3 = 50    (1050 °C hold 5 min)
```

## Status register 0x4D

```
bit 0-1 : 0 = run, 1 = stop, 2 = hold
bit 3   : 0 = auto, 1 = manual
```

A restored instrument reports `0x4D = 0x3F01` (auto + stop).
