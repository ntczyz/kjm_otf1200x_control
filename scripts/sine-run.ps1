# sine-run.ps1 -- sinusoidal temperature profile on AI-858 via host-side MV control.
#   T_ref(t) = Center - Amp*cos(2*pi*t/Period)   (starts at the bottom of the swing)
#   Phase 0: hold at Center-Amp until |PV-ref|<SettleC (or timeout)
#   Phase 1: follow the sine for Cycles periods
#   Then: MV=0, Srun=1 (stop), AMAn restored.
# SAFETY: PV > Center+Amp+MarginC or PV>MaxPV -> stop; comm loss -> stop;
#         finally block always writes MV=0, Srun=1, AMAn=1.
# Pure ASCII (Windows PowerShell 5.1).
[CmdletBinding()]
param(
  [string]$PortName = 'COM6',
  [int]$Baud = 19200,
  [int]$Addr = 1,
  [double]$CenterC = 300.0,
  [double]$AmpC = 50.0,
  [double]$PeriodMin = 35.0,
  [int]$Cycles = 2,
  [double]$AmbientC = 25.0,
  [double]$MarginC = 30.0,
  [double]$MaxPV = 900.0,
  [int]$MaxMV = 60,
  [double]$Kp = 0.8,
  [double]$Ki = 0.01,
  [double]$Kss = 0.044,
  [double]$Kramp = 0.75,
  [int]$PreheatTimeoutMin = 20,
  [switch]$Execute
)
$ErrorActionPreference = 'Continue'
function New-AibusRead([int]$a,[int]$code) {
  $cs = ($code * 256 + 0x52 + $a) -band 0xFFFF
  return [byte[]]([byte](0x80+$a),[byte](0x80+$a),[byte]0x52,[byte]$code,0,0,[byte]($cs -band 0xFF),[byte](($cs -shr 8) -band 0xFF))
}
function New-AibusWrite([int]$a,[int]$code,[int]$value) {
  $v = $value -band 0xFFFF
  $cs = ($code * 256 + 0x43 + $a + $v) -band 0xFFFF
  return [byte[]]([byte](0x80+$a),[byte](0x80+$a),[byte]0x43,[byte]$code,[byte]($v -band 0xFF),[byte](($v -shr 8) -band 0xFF),[byte]($cs -band 0xFF),[byte](($cs -shr 8) -band 0xFF))
}
function Read-Reply($sp,[int]$a) {
  $rx = New-Object System.Collections.ArrayList
  $sw = New-Object System.Diagnostics.Stopwatch; $sw.Start()
  while ($sw.ElapsedMilliseconds -lt 300) {
    while ($sp.BytesToRead -gt 0 -and $rx.Count -lt 64) { [void]$rx.Add([byte]$sp.ReadByte()) }
    Start-Sleep -Milliseconds 2
  }
  $r = $rx.ToArray()
  if ($r.Length -lt 10) { return $null }
  for ($o=0; $o -le ($r.Length-10); $o++) {
    $pv=[int]$r[$o]+256*[int]$r[$o+1]; $sv=[int]$r[$o+2]+256*[int]$r[$o+3]
    $mv=[int]$r[$o+4]; $st=[int]$r[$o+5]; $dat=[int]$r[$o+6]+256*[int]$r[$o+7]
    $crc=[int]$r[$o+8]+256*[int]$r[$o+9]
    if ((($pv+$sv+$mv+$st*256+$dat+$a) -band 0xFFFF) -eq $crc) {
      $mvs = if ($mv -gt 127) { $mv-256 } else { $mv }
      return [pscustomobject]@{ PV=$pv; SV=$sv; MV=$mvs; ST=$st; DAT=$dat }
    }
  }
  return $null
}
$stopOne = [System.IO.Ports.StopBits]::One
$sp = New-Object System.IO.Ports.SerialPort($PortName,$Baud,[System.IO.Ports.Parity]::Even,8,$stopOne)
$sp.ReadTimeout = 200; $sp.WriteTimeout = 400
$sp.DtrEnable = $false; $sp.RtsEnable = $false
$sp.Open()
$RdP = { param([int]$c) $sp.DiscardInBuffer(); $sp.Write((New-AibusRead $Addr $c),0,8); Read-Reply $sp $Addr }
$WrP = { param([int]$c,[int]$v) $sp.DiscardInBuffer(); $sp.Write((New-AibusWrite $Addr $c $v),0,8); Read-Reply $sp $Addr }

Write-Host "=================================================================="
Write-Host (" SINE run   center={0}C  amp=+/-{1}C  period={2}min  cycles={3}   EXECUTE={4}" -f $CenterC,$AmpC,$PeriodMin,$Cycles,$Execute)
Write-Host (" port={0} {1} 8E1 addr={2}  MV<={3}%  PV limit={4}C" -f $PortName,$Baud,$Addr,$MaxMV,$MaxPV)
Write-Host "=================================================================="
$d = & $RdP 0x0C
$dpt = if ($null -ne $d) { $d.DAT } else { 128 }
$decimals = if ($dpt -ge 128) { $dpt - 127 } else { $dpt }
$scale = [math]::Pow(10, $decimals)
$r0 = & $RdP 0x00
if ($null -eq $r0) { $sp.Close(); $sp.Dispose(); throw "no reply" }
$pv0 = $r0.PV / $scale
$bottom = $CenterC - $AmpC
$top = $CenterC + $AmpC
$maxSlope = 2 * [math]::PI * $AmpC / $PeriodMin
Write-Host (" start PV={0:N1}C   swing {1:N1}..{2:N1}C   max slope={3:N2}C/min" -f $pv0,$bottom,$top,$maxSlope)

if (-not $Execute) {
  Write-Host ""
  Write-Host ("DRY RUN: preheat to {0:N1}C, then {1} cycles of {2} min" -f $bottom,$Cycles,$PeriodMin)
  $sp.Close(); $sp.Dispose(); return
}

$logPath = Join-Path (Split-Path -Parent $PSScriptRoot) ("results\sine-{0}.csv" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($logPath, "elapsed_s,PV_C,target_C,MV_pct,err_C`r`n", $enc)
Write-Host (" log: " + $logPath)

$mvNow = 0; $iTerm = 0.0; $prevPv = $pv0; $commFail = 0; $abort = $null; $lastMvWrite = -100
& $WrP 0x18 0 | Out-Null     # manual mode
& $WrP 0x1B 0 | Out-Null     # RUN (required, else output stays disabled)
$t0 = Get-Date
$relLimit = [math]::Min($MaxPV, $top + $MarginC)
Write-Host (" started at {0}  (relLimit={1:N1}C)" -f (Get-Date -Format 'HH:mm:ss'), $relLimit)
$phase = 'preheat'

try {
  while ($true) {
    Start-Sleep -Milliseconds 1000
    $now = Get-Date
    $el = ($now - $t0).TotalSeconds
    $rd = & $RdP 0x00
    if ($null -eq $rd) { $commFail++; if ($commFail -ge 3) { $abort = 'comm lost'; break }; continue }
    $commFail = 0
    $pv = $rd.PV / $scale
    if ($pv -gt $MaxPV) { $abort = ('PV {0:N1} > MaxPV' -f $pv); break }
    if ($pv -gt $relLimit) { $abort = ('PV {0:N1} > limit {1:N1}' -f $pv, $relLimit); break }

    if ($phase -eq 'preheat') {
      $tRef = $bottom; $slope = 0.0
      if ([math]::Abs($pv - $bottom) -lt 3.0 -or $el -ge ($PreheatTimeoutMin * 60)) {
        $phase = 'sine'; $t0 = Get-Date; $el = 0
        Write-Host ("  preheat done at PV={0:N1}C -> sine starts ({1})" -f $pv, (Get-Date -Format 'HH:mm:ss'))
      }
    } else {
      $ph = 2 * [math]::PI * $el / ($PeriodMin * 60)
      $tRef = $CenterC - $AmpC * [math]::Cos($ph)
      $slope = $AmpC * (2 * [math]::PI / $PeriodMin) * [math]::Sin($ph)
      if ($el -ge ($Cycles * $PeriodMin * 60)) { break }
    }
    $err = $tRef - $pv
    $dPv = $pv - $prevPv; $prevPv = $pv
    $ff = $Kss * ($tRef - $AmbientC) + $Kramp * $slope
    $u = $ff + $Kp * $err + $iTerm
    if ($u -gt $MaxMV) { $u = $MaxMV } elseif ($u -lt 0) { $u = 0 }
    if ($u -gt 0 -and $u -lt $MaxMV) { $iTerm += $Ki * $err }
    $mvCmd = [int][math]::Round($u)
    # MV is allowed to be coarse/discontinuous: only write when the change is >=2%
    # and at least 5 s passed since the previous write. The instrument holds the last value.
    if ($mvCmd -ne $mvNow -and [math]::Abs($mvCmd - $mvNow) -ge 2 -and ($el - $lastMvWrite) -ge 5) {
      $wr = & $WrP 0x1A $mvCmd
      if ($null -ne $wr) { $mvNow = $mvCmd; $lastMvWrite = $el }
    }
    $line = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.0},{1:0.000},{2:0.000},{3},{4:0.000}", $el, $pv, $tRef, $mvNow, $err)
    [System.IO.File]::AppendAllText($logPath, $line + "`r`n", $enc)
    if (([int]$el % 30) -eq 0) { Write-Host ("  t={0,5:N0}s  PV={1,6:N1}C  ref={2,6:N1}C  err={3,5:N1}  MV={4}%" -f $el,$pv,$tRef,$err,$mvNow) }
  }
} finally {
  & $WrP 0x1A 0 | Out-Null
  Start-Sleep -Milliseconds 200
  & $WrP 0x1B 1 | Out-Null
  Start-Sleep -Milliseconds 300
  # restoring the pre-experiment state: writing Srun=0 switches the instrument
  # from MANUAL back to AUTO (verified 2026-11-12), then stop again and put FSV back.
  & $WrP 0x18 1 | Out-Null
  Start-Sleep -Milliseconds 400
  & $WrP 0x1B 0 | Out-Null
  Start-Sleep -Milliseconds 900
  & $WrP 0x1B 1 | Out-Null
  Start-Sleep -Milliseconds 600
  & $WrP 0x18 2 | Out-Null
  Start-Sleep -Milliseconds 500
  $fin = & $RdP 0x00
  Write-Host ""
  Write-Host ("-------- SINE END: PV={0:N1}C  MV={1}  abort={2} --------" -f $(if($null -ne $fin){$fin.PV/$scale}else{-999}),$(if($null -ne $fin){$fin.MV}else{'?'}),$abort)
  Write-Host (" log: " + $logPath)
  $sp.Close(); $sp.Dispose()
}
