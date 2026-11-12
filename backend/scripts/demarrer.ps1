<#
.SYNOPSIS
    Démarre le serveur LIMS (uvicorn, API + interface construite) — voir docs/deploiement.md.

.DESCRIPTION
    - lance « python -m uvicorn app.main:app » avec l'environnement Python du projet (backend\.venv) ;
    - la configuration (base, clé secrète, environnement, dossiers) vient de backend\.env ;
    - refuse de démarrer si le port est déjà occupé (serveur déjà lancé ?) ;
    - HTTPS : -CertFile et -KeyFile (voir docs/https.md) ;
    - -InstallerTache : enregistre la tâche planifiée Windows « LIMS - serveur » qui lance ce script
      au démarrage de l'ordinateur (compte SYSTEM, relance automatique en cas d'arrêt). À exécuter
      une seule fois, dans une console PowerShell ouverte « en tant qu'administrateur ».

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File backend\scripts\demarrer.ps1
    powershell -ExecutionPolicy Bypass -File backend\scripts\demarrer.ps1 -Port 8443 -CertFile D:\LIMS\tls\serveur.crt -KeyFile D:\LIMS\tls\serveur.key
    powershell -ExecutionPolicy Bypass -File backend\scripts\demarrer.ps1 -InstallerTache
#>
[CmdletBinding()]
param(
    [string]$Hote = "0.0.0.0",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$CertFile = "",
    [string]$KeyFile = "",
    [switch]$InstallerTache,
    [string]$NomTache = "LIMS - serveur"
)

$ErrorActionPreference = "Stop"
$Backend = Split-Path -Parent $PSScriptRoot
$Racine = Split-Path -Parent $Backend
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Environnement Python introuvable : $Python (docs/deploiement.md, étape « Environnement Python »)."
}
if (-not (Test-Path (Join-Path $Backend ".env")) -and -not $env:DATABASE_URL) {
    throw "Fichier backend\.env absent : copiez backend\.env.exemple en backend\.env et remplissez-le."
}
if (($CertFile -and -not $KeyFile) -or ($KeyFile -and -not $CertFile)) {
    throw "HTTPS : indiquez à la fois -CertFile et -KeyFile."
}

if ($InstallerTache) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Hote $Hote -Port $Port"
    if ($CertFile) { $arguments += " -CertFile `"$CertFile`" -KeyFile `"$KeyFile`"" }
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $Backend
    $declencheur = New-ScheduledTaskTrigger -AtStartup
    $reglages = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 `
        -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName $NomTache -Action $action -Trigger $declencheur -Settings $reglages `
        -Principal $principal -Description "Serveur LIMS LRARVY (uvicorn), port $Port" -Force | Out-Null
    Write-Output "Tâche planifiée « $NomTache » enregistrée : le serveur démarrera avec Windows (port $Port)."
    Write-Output "Démarrage immédiat : Start-ScheduledTask -TaskName '$NomTache'"
    exit 0
}

$occupe = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($occupe) {
    throw "Le port $Port est déjà utilisé (processus $($occupe[0].OwningProcess)) : le serveur tourne-t-il déjà ?"
}
if (-not (Test-Path (Join-Path $Racine "frontend\dist\index.html"))) {
    Write-Warning "frontend\dist\index.html absent : l'interface ne sera pas servie (npm run build dans frontend\)."
}

Set-Location $Backend
$arguments = @("-m", "uvicorn", "app.main:app", "--host", $Hote, "--port", "$Port")
if ($CertFile) { $arguments += @("--ssl-certfile", $CertFile, "--ssl-keyfile", $KeyFile) }
Write-Output ("{0}  Démarrage du serveur LIMS sur {1}:{2}{3}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Hote, $Port,
    $(if ($CertFile) { " (HTTPS)" } else { "" }))
& $Python @arguments
exit $LASTEXITCODE
