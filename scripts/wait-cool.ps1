# wait-cool.ps1 -- READ-ONLY watcher: poll PV until it drops to TargetC, then exit.
# Sends NO commands to the instrument. Logs to CSV.
# Pure ASCII (Windows PowerShell 5.1).
[CmdletBinding()]
param(
  [string]$PortName = 'COM6',
  [int]$Baud = 19200,
  [int]$Addr = 1,
  [double]$TargetC = 30.0,
  [int]$PeriodSec = 10,
  [int]$MaxMinutes = 180
)
$ErrorActionPreference = 'Continue'
function New-AibusRead([int]$a, [int]$code) {
  $cs = ($code * 256 + 0x52 + $a) -band 0xFFFF
  return [byte[]]([byte](0x80+$a), [byte](0x80+$a), [byte]0x52, [byte]$code, 0, 0, [byte]($cs -band 0xFF), [byte](($cs -shr 8) -band 0xFF))
}
function Read-Reply($sp, [int]$a) {
  $rx = New-Object System.Collections.ArrayList
  $sw = New-Object System.Diagnostics.Stopwatch; $sw.Start()
  while ($sw.ElapsedMilliseconds -lt 300) {
    while ($sp.BytesToRead -gt 0 -and $rx.Count -lt 64) { [void]$rx.Add([byte]$sp.ReadByte()) }
    Start-Sleep -Milliseconds 2
  }
  $r = $rx.ToArray()
  if ($r.Length -lt 10) { return $null }
  for ($o = 0; $o -le ($r.Length - 10); $o++) {
    $pv = [int]$r[$o] + 256*[int]$r[$o+1]; $sv = [int]$r[$o+2] + 256*[int]$r[$o+3]
    $mv = [int]$r[$o+4]; $st = [int]$r[$o+5]; $dat = [int]$r[$o+6] + 256*[int]$r[$o+7]
    $crc = [int]$r[$o+8] + 256*[int]$r[$o+9]
    if ((($pv + $sv + $mv + $st*256 + $dat + $a) -band 0xFFFF) -eq $crc) {
      return [pscustomobject]@{ PV=$pv; SV=$sv; MV=$mv; ST=$st; DAT=$dat }
    }
  }
  return $null
}
$stopOne = [System.IO.Ports.StopBits]::One
$sp = New-Object System.IO.Ports.SerialPort($PortName, $Baud, [System.IO.Ports.Parity]::Even, 8, $stopOne)
$sp.ReadTimeout = 200; $sp.WriteTimeout = 400
$sp.DtrEnable = $false; $sp.RtsEnable = $false
$sp.Open()
$enc = New-Object System.Text.UTF8Encoding($false)
$logPath = Join-Path (Split-Path -Parent $PSScriptRoot) ("results\cooldown-{0}.csv" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
[System.IO.File]::WriteAllText($logPath, "timestamp,elapsed_s,PV_C`r`n", $enc)
Write-Host ("=== cooldown watcher  {0}  target {1}C  (read-only) ===" -f $PortName, $TargetC)
$t0 = Get-Date
$fail = 0
$last = $null
while (((Get-Date) - $t0).TotalMinutes -lt $MaxMinutes) {
  $sp.DiscardInBuffer(); $sp.Write((New-AibusRead $Addr 0x00), 0, 8)
  $d = Read-Reply $sp $Addr
  if ($null -ne $d) {
    $fail = 0
    $pv = $d.PV / 10.0
    $line = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0},{1:0.0},{2:0.0}", (Get-Date -Format 'HH:mm:ss'), ((Get-Date) - $t0).TotalSeconds, $pv)
    [System.IO.File]::AppendAllText($logPath, $line + "`r`n", $enc)
    if ($null -eq $last -or [math]::Abs($pv - $last) -ge 0.5) { Write-Host ("  " + $line); $last = $pv }
    if ($pv -le $TargetC) { Write-Host ("  REACHED {0}C at {1}" -f $pv, (Get-Date -Format 'HH:mm:ss')); break }
  } else {
    $fail++
    Write-Host ("  [comm fail {0}/3]" -f $fail)
    if ($fail -ge 3) { Write-Host "  3 consecutive failures -> abort watcher"; break }
  }
  Start-Sleep -Seconds $PeriodSec
}
$sp.Close(); $sp.Dispose()
Write-Host ("done. log: " + $logPath)
