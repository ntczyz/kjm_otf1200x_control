---
name: yudian-aibus-furnace
description: Read, control, and log Yudian (宇电) AI-series furnace controllers (AI-858, AI-518P) over RS485 using the AIBUS protocol — decode PV/SV/MV correctly, run ramp/hold/cooldown profiles, compare instrument-SV vs host-PID control, build live web dashboards, and produce publication-style cooling comparison figures. Use when a tube furnace / muffle furnace / kiln has a Yudian AI-series controller and the task involves communication, temperature profiling, or data logging.
---

# Yudian AIBUS furnace control

Tested on a MTI OTF-1200X tube furnace with a Yudian **AI-858** controller
(Addr=1, 19200, 8E1, AIBUS). Everything below was verified on real hardware.

## When to use

- "Can't read the furnace over RS485", zero-byte / garbage replies, CRC errors.
- "Ramp to X °C in Y minutes, hold, stop, log the cooldown."
- Comparing control strategies (instrument setpoint vs host PID).
- Building a live web dashboard or an interactive report from the logged CSV.

## Quick start

```powershell
# single read: PV / SV / MV / status  (the reader that actually works)
.\scripts\aibus-read.ps1 -PortName COM6 -Baud 19200 -Framing 8E1 -Addr 1
```

```powershell
# full profile: 25 -> 700 °C in 15 min, hold 5, stop, log to 100 °C
.\scripts\profile-700.ps1 -PortName COM6 -TargetC 700 -SPrCpm 45 -HoldMin 5 `
                         -CoolToC 100 -MaxPowerPct 80 -Execute
```

```powershell
# live dashboard (no page reload, hover stays active while data updates)
python .\scripts\live-server.py <results-dir> 8765
# then open http://127.0.0.1:8765/live.html
```

## Protocol essentials (the part everyone gets wrong)

**READ** request is 8 bytes, sent as `(0x80+addr)×2, 0x52, param, 0x00, 0x00, CRC_lo, CRC_hi`
with `CRC = param*256 + 0x52 + addr`.

**The reply is 10 bytes with NO header**:

```
PV(2) SV(2) MV(1) STATUS(1) DATA(2) CRC(2)      little-endian
CRC = PV + SV + MV + STATUS*256 + DATA + Addr
```

> The common failure: a decoder that looks for a `0x81 0x81 0x52` header discards
> every valid reply and reports "no data". Scan 10-byte windows and validate the
> CRC instead — the reply starts directly with the PV low byte.

**WRITE** is 8 bytes: `(0x80+addr)×2, 0x43, param, val_lo, val_hi, CRC_lo, CRC_hi`
with `CRC = param*256 + 0x43 + addr + val`.

Details, parameter tables: [`references/aibus-protocol.md`](references/aibus-protocol.md).

## Control routes

| Route | How | Verdict |
|---|---|---|
| **A — instrument** | `Pno=0`, `SPr=<rate×10>`, `SV=<target>`, `Srun=0` | **Preferred**: overshoot 2.5 %, hold σ 2.1 °C |
| **B — host PID** | write MV (0x1A) every ~1 s from a host loop | overshoot 3.8 %, hold σ 6.5 °C — worse, and risks the wireless/port link |

For Route A the instrument owns the ramp; the host only logs and stops it.
`SPr` unit is **0.1 °C/min** (45 °C/min ⇒ `SPr=450`).

## Safety and restore (do this after every manual/MV run)

```
MV=0 → Srun=1 → AMAn=1 → Srun=0 (forces AUTO) → Srun=1 (stop) → AMAn=2 (FSV)
```

Then verify: all parameters match the pre-run backup (55 params, 0 diff) and
`0x4D` reports AUTO + STOP. Always take a parameter backup before touching
anything. `scripts/profile-700.ps1` does this automatically in a `finally` block.

## Pitfalls — read [`references/pitfalls.md`](references/pitfalls.md)

The top five, all of which cost real debugging time:

1. **Reply has no header** — see above.
2. **`SPr` is 0.1 °C/min** — `SPr=27` gives 2.7 °C/min, not 27.
3. **`StoP` state disables output** even in manual mode — write `Srun=0` for MV
   to reach the heater. Writing `AMAn` alone does **not** flip manual→auto;
   `Srun=0` does.
4. **`bAud` 0/1/2/3/4/8/12 re-purposes the COMM port** (4–20 mA / switch input /
   alarm output) — no comms at all. Keep `bAud=0` (19200).
5. **`dPt` write range is 0–3, read adds +127**: write `0` → reads `128`
   (communicate at 1 decimal, display without a decimal); write `1` → reads `1`
   (display shows 0.1 °C). Writing `128` is wrong and gets clamped to `1`.

## Files

```
SKILL.md                      this file
references/aibus-protocol.md  frames, checksums, register map, worked example
references/ai858-parameters.md  AFC / bAud / dPt / SPr / OPH / Srun tables
references/pitfalls.md        all traps found on real hardware
references/troubleshooting.md  zero-byte / garbage diagnosis tree
scripts/aibus-read.ps1        correct reader (headerless reply + CRC)
scripts/profile-700.ps1       ramp → hold → stop → cooldown logger + restore
scripts/sine-run.ps1          sine tracking experiment
scripts/wait-cool.ps1         wait-for-cooldown helper
scripts/live-server.py        HTTP server: /live.html + /data.csv (newest run)
scripts/live.html             canvas dashboard: 2 s fetch, crosshair hover
scripts/make-report-page.py   interactive report (canvas, crosshair, 2-exp fits)
scripts/compare-cooling.py    Origin-style multi-run cooling comparison (Arial)
scripts/analyze-run.py        post-run statistics
scripts/plot-run.py           quick PNG plot
```

## Notes

- The scripts are Windows PowerShell 5.1; Python parts need only the stdlib
  plus Pillow (and numpy for the report/fit generators).
- Serial adapters re-enumerate across reboots — re-check the port name with
  `[System.IO.Ports.SerialPort]::GetPortNames()` before every run.
- For a 2-wire RS485 link you need an adapter that actually drives DE/RE
  (a plain FTDI/PL2303 USB-UART with TX/RX bridged can work, but verify).
