# yudian-aibus-furnace

Control and log a Yudian (宇电) **AI-series** furnace controller over RS485 using
the **AIBUS** protocol — with the field-tested fixes for the traps that make it
look like "the furnace doesn't answer".

Built while bringing a MTI OTF-1200X tube furnace (Yudian **AI-858**, address 1,
19200 8E1) from "zero replies" to reliable profiled runs:

- 25 → 700 °C in **15.2 min** (three consecutive runs, all on target)
- 5 min hold at **700.1 ± 1.2 °C**
- logged cooldown to 100 °C, with a live web dashboard and an interactive report

## What's inside

This repository is a **DeepSeek Harness skill** (`SKILL.md` + `references/` +
`scripts/`). It also works as a plain collection of scripts.

| Path | Purpose |
|---|---|
| `SKILL.md` | the skill: when to use, quick start, protocol essentials, pitfalls |
| `references/aibus-protocol.md` | frames, checksums, register map, worked example |
| `references/ai858-parameters.md` | AFC / bAud / dPt / SPr / OPH / Srun tables |
| `references/pitfalls.md` | 14 traps found on real hardware |
| `references/troubleshooting.md` | the zero-byte → garbage → wrong-value diagnosis tree |
| `scripts/aibus-read.ps1` | single/full read of PV, SV, MV and 55 parameters |
| `scripts/profile-700.ps1` | ramp → hold → stop → cooldown logger, with full restore |
| `scripts/sine-run.ps1` | sine setpoint tracking experiment |
| `scripts/live-server.py` | HTTP server (`/live.html`, `/data.csv`) for the dashboard |
| `scripts/live.html` | canvas dashboard, 2 s fetch, hover crosshair survives updates |
| `scripts/make-report-page.py` | interactive report: crosshair, tooltips, two-exp fits |
| `scripts/compare-cooling.py` | Origin-style multi-run cooling figure (Arial, boxed legend) |
| `scripts/analyze-run.py`, `plot-run.py` | post-run statistics and quick PNG |

## The one thing to know

The AIBUS reply is **10 bytes with no header**:

```
PV(2) SV(2) MV(1) STATUS(1) DATA(2) CRC(2)      little-endian
CRC = PV + SV + MV + STATUS*256 + DATA + Addr
```

A decoder that waits for a `0x81 0x81 0x52` header never sees a reply. Scan
10-byte windows and validate the CRC instead.

## Quick start

```powershell
# read
.\scripts\aibus-read.ps1 -PortName COM6 -Baud 19200 -Framing 8E1 -Addr 1

# profiled run (dry-run first: drop -Execute)
.\scripts\profile-700.ps1 -PortName COM6 -TargetC 700 -SPrCpm 45 -HoldMin 5 `
                         -CoolToC 100 -MaxPowerPct 80 -Execute

# live dashboard
python .\scripts\live-server.py .\results 8765
# open http://127.0.0.1:8765/live.html
```

## Requirements

- Windows PowerShell 5.1 for the `.ps1` scripts (they use `System.IO.Ports`).
- Python 3.9+ for the live server / reports / figures (`Pillow`; `numpy` for the
  report and fits).
- A working RS485 link to the instrument (19200 8E1, AIBUS).

## Safety

The instrument controls a heater. Before running anything:

1. Take a full parameter backup (the scripts do it for you).
2. Run once **without `-Execute`** — every script supports a dry-run summary.
3. After any manual/MV run, restore:
   `MV=0 → Srun=1 → AMAn=1 → Srun=0 → Srun=1 → AMAn=2`, then diff all 55
   parameters against the backup.

## License

MIT — see [LICENSE](LICENSE).
