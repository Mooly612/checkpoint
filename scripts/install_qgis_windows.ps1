# Installs only into a disposable CI runner; never run on an existing QGIS root.
param(
    [Parameter(Mandatory)][ValidateSet('3.44', '4.0', '4.2')][string]$Release,
    [Parameter(Mandatory)][string]$Root
)
$ErrorActionPreference = 'Stop'
if (Test-Path $Root) { throw "Refusing to replace existing installation: $Root" }
$versions = @{ '3.44' = '3.44.15-2'; '4.0' = '4.0.3-1'; '4.2' = '4.2.3-2' }
$name = "QGIS-OSGeo4W-$($versions[$Release]).msi"
$url = "https://download.qgis.org/downloads/$name"
$installer = Join-Path $env:RUNNER_TEMP $name
$log = Join-Path $env:RUNNER_TEMP 'qgis-install.log'
Write-Host "Downloading released QGIS $Release from $url"
Invoke-WebRequest -Uri $url -OutFile $installer
$checksumFile = Join-Path $env:RUNNER_TEMP "$name.sha256sum"
Invoke-WebRequest -Uri ($url -replace '\.msi$', '.sha256sum') -OutFile $checksumFile
$checksum = Get-Content -Raw $checksumFile
$match = [regex]::Match($checksum, '\b[a-fA-F0-9]{64}\b')
if (-not $match.Success) { throw 'Official SHA-256 checksum missing' }
if ((Get-FileHash $installer -Algorithm SHA256).Hash -ne $match.Value) {
    throw 'QGIS installer SHA-256 mismatch'
}
$arguments = @('/i', "`"$installer`"", '/qn', '/norestart', "INSTALLDIR=`"$Root`"", '/L*v', "`"$log`"")
$process = Start-Process msiexec.exe -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -notin @(0, 3010)) { throw "QGIS install failed: $($process.ExitCode); see $log" }
$launchers = @(Get-ChildItem (Join-Path $Root 'bin') -Filter 'python-qgis*.bat' |
    Where-Object { $_.Name -notmatch 'dev' })
if ($launchers.Count -ne 1) { throw "Expected one QGIS Python launcher in $Root/bin" }
# Only stdout is the launcher path; messages use Write-Host.
$launchers[0].FullName
