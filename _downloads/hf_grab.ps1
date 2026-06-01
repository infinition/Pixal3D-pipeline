param(
    [Parameter(Mandatory=$true)][string]$Base,
    [Parameter(Mandatory=$true)][string[]]$Repos,
    [string]$Exclude,
    [switch]$Flat
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$token = $env:HF_TOKEN
$authHeaders = @{}
if ($token) { $authHeaders['Authorization'] = "Bearer $token" }

function Get-Tree($repo) {
    $url = "https://huggingface.co/api/models/$repo/tree/main?recursive=true"
    return Invoke-RestMethod -Uri $url -Headers $authHeaders -TimeoutSec 60
}

function Download-File($url, $dest, $expectedSize) {
    $part = "$dest.part"
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        $existing = 0
        if (Test-Path $part) { $existing = (Get-Item $part).Length }
        if ($existing -gt $expectedSize) { Remove-Item $part -Force; $existing = 0 }
        if ($existing -eq $expectedSize) { break }
        $fs = $null; $resp = $null; $stream = $null
        try {
            $req = [System.Net.HttpWebRequest]::Create($url)
            if ($token) { $req.Headers.Add('Authorization', "Bearer $token") }
            $req.AllowAutoRedirect = $true
            $req.Timeout = 60000
            $req.ReadWriteTimeout = 120000
            if ($existing -gt 0) { $req.AddRange([long]$existing) }
            $resp = $req.GetResponse()
            $append = ($existing -gt 0 -and [int]$resp.StatusCode -eq 206)
            if (-not $append) { $existing = 0 }
            $fs = [System.IO.File]::Open($part, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
            if ($append) {
                $fs.Close()
                $fs = [System.IO.File]::Open($part, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write)
                $fs.Seek($existing, [System.IO.SeekOrigin]::Begin) | Out-Null
            }
            $stream = $resp.GetResponseStream()
            $buf = New-Object byte[] (4194304)
            $total = $existing
            $mark = $existing
            $sw = [Diagnostics.Stopwatch]::StartNew()
            while (($n = $stream.Read($buf, 0, $buf.Length)) -gt 0) {
                $fs.Write($buf, 0, $n)
                $total += $n
                if (($total - $mark) -ge 524288000) {
                    $mbps = if ($sw.Elapsed.TotalSeconds -gt 0) { ($total - $existing) / 1MB / $sw.Elapsed.TotalSeconds * 8 } else { 0 }
                    Write-Output ("      {0} / {1} MB  ({2} Mbps)" -f [math]::Round($total/1MB), [math]::Round($expectedSize/1MB), [math]::Round($mbps))
                    $mark = $total
                }
            }
            $fs.Close(); $fs = $null
            $resp.Close(); $resp = $null
            $got = (Get-Item $part).Length
            if ($got -eq $expectedSize) { break }
            Write-Output ("      taille incomplete ($got/$expectedSize), reprise...")
        } catch {
            if ($fs) { try { $fs.Close() } catch {} }
            if ($resp) { try { $resp.Close() } catch {} }
            Write-Output ("      tentative $attempt echouee: " + $_.Exception.Message)
            Start-Sleep -Seconds 3
        }
    }
    $final = (Get-Item $part -EA SilentlyContinue)
    if ($final -and $final.Length -eq $expectedSize) {
        Move-Item -Force $part $dest
        return $true
    }
    return $false
}

$grandOk = 0; $grandSkip = 0; $grandFail = 0
foreach ($repo in $Repos) {
    $repoDest = if ($Flat) { $Base } else { Join-Path $Base ($repo -replace '/', '_') }
    Write-Output ""
    Write-Output ("==== REPO $repo  ->  $repoDest ====")
    try { $tree = Get-Tree $repo } catch {
        Write-Output ("  ERREUR tree API: " + $_.Exception.Message + "  (repo ignore)")
        continue
    }
    $files = $tree | Where-Object { $_.type -eq 'file' }
    $totGB = [math]::Round((($files | Measure-Object size -Sum).Sum)/1GB, 2)
    Write-Output ("  $($files.Count) fichiers, $totGB GB")
    foreach ($f in ($files | Sort-Object size)) {
        if ($Exclude -and $f.path -match $Exclude) {
            Write-Output ("  IGNORE  $($f.path)")
            continue
        }
        $local = Join-Path $repoDest ($f.path -replace '/', '\')
        $dir = Split-Path $local -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
        if ((Test-Path $local) -and ((Get-Item $local).Length -eq $f.size)) {
            Write-Output ("  SKIP  $($f.path)  (deja complet)")
            $grandSkip++
            continue
        }
        $mb = [math]::Round($f.size/1MB, 1)
        Write-Output ("  GET   $($f.path)  ($mb MB)")
        $url = "https://huggingface.co/$repo/resolve/main/$($f.path)"
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $ok = Download-File $url $local $f.size
        $sw.Stop()
        if ($ok) {
            $spd = if ($sw.Elapsed.TotalSeconds -gt 0) { [math]::Round($f.size/1MB/$sw.Elapsed.TotalSeconds,1) } else { 0 }
            Write-Output ("  DONE  $($f.path)  ($mb MB en $([math]::Round($sw.Elapsed.TotalSeconds))s, $spd MB/s)")
            $grandOk++
        } else {
            Write-Output ("  FAIL  $($f.path)  (echec apres reprises)")
            $grandFail++
        }
    }
}
Write-Output ""
Write-Output ("===== TERMINE : $grandOk telecharges, $grandSkip deja presents, $grandFail echecs =====")
if ($grandFail -gt 0) { exit 1 } else { exit 0 }
