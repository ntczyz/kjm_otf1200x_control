# profile-700.ps1 -- ramp to TargetC (instrument SV + SPr), hold, stop, then keep logging
#                    the natural cooldown until PV drops to CoolToC.
#   Phase 1 RAMP : Pno=0, SPr=<rate*10>, SV=TargetC, Srun=0 ; log until PV >= TargetC-2
#   Phase 2 HOLD : HoldMin minutes at TargetC
#   Phase 3 STOP : Srun=1 ; keep logging until PV <= CoolToC
#   Finally      : restore the pre-experiment state (Pno=50, SPr=0, SV=0, Srun=1, AUTO, AMAn=2)
# Pure ASCII (Windows PowerShell 5.1).
[CmdletBinding()]
param(
  [string]$PortName = 'COM6',
  [int]$Baud = 19200,
  [int]$Addr = 1,
  [double]$TargetC = 700.0,
  [double]$SPrCpm = 45.0,
  [int]$HoldMin = 5,
  [double]$CoolToC = 100.0,
  [double]$MaxPV = 900.0,
  [double]$MarginC = 50.0,
  [int]$MaxRunMin = 300,
  [double]$MaxPowerPct = 0,
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
Write-Host (" PROFILE  ramp->{0}C  SPr={1}C/min  hold={2}min  cool-log->{3}C   EXECUTE={4}" -f $TargetC,$SPrCpm,$HoldMin,$CoolToC,$Execute)
Write-Host (" port={0} {1} 8E1 addr={2}   MaxPV={3}C  limit={4}C" -f $PortName,$Baud,$Addr,$MaxPV,($TargetC+$MarginC))
Write-Host "=================================================================="
$d = & $RdP 0x0C
$dpt = if ($null -ne $d) { $d.DAT } else { 128 }
$decimals = if ($dpt -ge 128) { $dpt - 127 } else { $dpt }
$scale = [math]::Pow(10, $decimals)
$r0 = & $RdP 0x00
if ($null -eq $r0) { $sp.Close(); $sp.Dispose(); throw "no reply" }
$pv0 = $r0.PV / $scale
$tgtRaw = [int][math]::Round($TargetC * $scale)
$sprRaw = [int][math]::Round($SPrCpm * 10)   # SPr unit = 0.1 C/min (verified)
$limit = [math]::Min($MaxPV, $TargetC + $MarginC)
Write-Host (" start PV={0:N1}C  target={1:N1}C  SPr raw={2} ({3}C/min)  limit={4:N1}C" -f $pv0,$TargetC,$sprRaw,$SPrCpm,$limit)
if (-not $Execute) {
  Write-Host "DRY RUN: would write Pno=0, SPr=$sprRaw, SV=$tgtRaw, Srun=0; hold $HoldMin min after PV reaches $TargetC; then stop and log until $CoolToC C."
  $sp.Close(); $sp.Dispose(); return
}

$logPath = Join-Path (Split-Path -Parent $PSScriptRoot) ("results\profile700-{0}.csv" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($logPath, "elapsed_s,PV_C,SV_C,MV_pct,phase`r`n", $enc)
Write-Host (" log: " + $logPath)

$phase = 'ramp'
$holdStart = $null
$t0 = Get-Date
$commFail = 0
$abort = $null
$origOph = $null
Write-Host (" START {0}" -f (Get-Date -Format 'HH:mm:ss'))

try {
  if ($MaxPowerPct -gt 0) {
    $o = & $RdP 0x13
    if ($null -ne $o) { $origOph = [int]$o.DAT }
    & $WrP 0x13 ([int][math]::Round($MaxPowerPct)) | Out-Null
    Write-Host ("  OPH={0}% (was {1}%)" -f $MaxPowerPct, $origOph)
  }
  & $WrP 0x2B 0 | Out-Null
  Write-Host "  Pno=0 (program off)"
  & $WrP 0x2A $sprRaw | Out-Null
  Write-Host ("  SPr={0} ({1}C/min)" -f $sprRaw,$SPrCpm)
  & $WrP 0x00 $tgtRaw | Out-Null
  Write-Host ("  SV={0}C" -f $TargetC)
  & $WrP 0x1B 0 | Out-Null
  Write-Host "  Srun=0 (run)"

  while ($true) {
    Start-Sleep -Milliseconds 1000
    $now = Get-Date
    $el = ($now - $t0).TotalSeconds
    $rd = & $RdP 0x00
    if ($null -eq $rd) { $commFail++; if ($commFail -ge 3) { $abort = 'comm lost'; break }; continue }
    $commFail = 0
    $pv = $rd.PV / $scale
    $svLive = $rd.SV / $scale
    if ($pv -gt $MaxPV) { $abort = ('PV {0:N1} > MaxPV' -f $pv); break }
    if ($pv -gt $limit) { $abort = ('PV {0:N1} > limit {1:N1}' -f $pv, $limit); break }

    if ($phase -eq 'ramp' -and $pv -ge ($TargetC - 2.0)) {
      $phase = 'hold'; $holdStart = $now
      Write-Host ("  reached {0:N1}C at t={1:N1} min -> HOLD {2} min ({3})" -f $pv, ($el/60), $HoldMin, (Get-Date -Format 'HH:mm:ss'))
    } elseif ($phase -eq 'hold' -and (($now - $holdStart).TotalMinutes -ge $HoldMin)) {
      & $WrP 0x1B 1 | Out-Null
      $phase = 'cool'
      Write-Host ("  hold finished -> Srun=1 (stop), logging cooldown until {0}C ({1})" -f $CoolToC, (Get-Date -Format 'HH:mm:ss'))
    } elseif ($phase -eq 'cool' -and $pv -le $CoolToC) {
      Write-Host ("  reached {0:N1}C  -> DONE at t={1:N1} min" -f $pv, ($el/60))
      break
    }
    if ($el -ge ($MaxRunMin * 60)) { $abort = 'MaxRunMin'; break }

    $line = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.0},{1:0.000},{2:0.000},{3},{4}", $el, $pv, $svLive, $rd.MV, $phase)
    [System.IO.File]::AppendAllText($logPath, $line + "`r`n", $enc)
    if (([int]$el % 60) -eq 0) { Write-Host ("  t={0,6:N1}min  PV={1,6:N1}C  SV={2,6:N1}C  MV={3,3}%  [{4}]" -f ($el/60),$pv,$svLive,$rd.MV,$phase) }
  }
} finally {
  # restore the pre-experiment state
  & $WrP 0x1B 1 | Out-Null
  Start-Sleep -Milliseconds 300
  if ($null -ne $origOph) { & $WrP 0x13 $origOph | Out-Null }
  & $WrP 0x2A 0 | Out-Null        # SPr back to 0
  & $WrP 0x00 0 | Out-Null        # SV back to 0
  Start-Sleep -Milliseconds 300
  & $WrP 0x2B 50 | Out-Null       # Pno back to 50
  Start-Sleep -Milliseconds 300
  & $WrP 0x18 1 | Out-Null
  Start-Sleep -Milliseconds 400
  & $WrP 0x1B 0 | Out-Null        # run -> forces AUTO
  Start-Sleep -Milliseconds 900
  & $WrP 0x1B 1 | Out-Null        # stop
  Start-Sleep -Milliseconds 600
  & $WrP 0x18 2 | Out-Null        # AMAn back to 2 (FSV)
  Start-Sleep -Milliseconds 500
  $fin = & $RdP 0x00
  $st4 = & $RdP 0x4D
  Write-Host ""
  Write-Host "-------- DONE --------"
  Write-Host (" PV={0:N1}C  MV={1}  abort={2}" -f $(if($null -ne $fin){$fin.PV/$scale}else{-999}),$(if($null -ne $fin){$fin.MV}else{'?'}),$abort)
  if ($null -ne $st4) { $v=[int]$st4.DAT; Write-Host (" 0x4D=0x{0:X4}  {1}  {2}" -f $v,$(if((($v -shr 3)-band 1) -eq 1){'MANUAL'}else{'AUTO'}),$(if(($v -band 3) -eq 1){'stopped'}else{'running'})) }
  Write-Host (" log: " + $logPath)
  $sp.Close(); $sp.Dispose()
}
