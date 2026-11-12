<#
.SYNOPSIS
    Met à jour le LIMS sur le serveur du labo — voir docs/deploiement.md, « Mise à jour ».

.DESCRIPTION
    Étapes, dans l'ordre ; la mise à jour s'arrête à la première erreur (avec le moyen du retour arrière) :
      1. sauvegarde de la base (scripts\sauvegarde.ps1) — obligatoire sauf -SansSauvegarde ;
      2. copie de la version en place (code, sans .env, .venv, node_modules ni journaux) dans
         <DossierVersions>\<horodatage>, pour un retour arrière ;
      3. copie des fichiers de la nouvelle version depuis -Source (facultatif : sinon, les fichiers
         ont déjà été remplacés à la main) ;
      4. arrêt du serveur (tâche planifiée, puis processus qui écoute sur le port) ;
      5. dépendances Python (pip install -r requirements.txt) ;
      6. migrations de la base (scripts\migrer.py) ;
      7. interface (npm install puis npm run build dans frontend\) ;
      8. redémarrage (tâche planifiée si elle existe, sinon scripts\demarrer.ps1 en arrière-plan) ;
      9. vérification : GET /api/health (base, version, dernière sauvegarde).
    Journal : backend\logs\mise_a_jour.log.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File backend\scripts\mettre_a_jour.ps1 -Source E:\LIMS-2.1.0
#>
[CmdletBinding()]
param(
    [string]$Base = "labo",
    [string]$DossierSauvegarde = $(if ($env:LIMS_SAUVEGARDE_DIR) { $env:LIMS_SAUVEGARDE_DIR } else { "D:\Sauvegardes\labo" }),
    [string]$DossierVersions = "D:\LIMS\versions",
    [string]$Source = "",
    [string]$NomTache = "LIMS - serveur",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$UrlSante = "",
    [switch]$SansSauvegarde,
    [switch]$SansRedemarrage
)

$ErrorActionPreference = "Stop"
$Backend = Split-Path -Parent $PSScriptRoot
$Racine = Split-Path -Parent $Backend
$Frontend = Join-Path $Racine "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$Horodatage = Get-Date -Format "yyyy-MM-dd_HHmmss"
if (-not $UrlSante) { $UrlSante = "http://127.0.0.1:$Port/api/health" }
New-Item -ItemType Directory -Force -Path (Join-Path $Backend "logs") | Out-Null
$Journal = Join-Path $Backend "logs\mise_a_jour.log"
$etape = 0

function Ecrire([string]$message) {
    $ligne = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Write-Output $ligne
    Add-Content -Path $Journal -Value $ligne -Encoding UTF8
}
function Etape([string]$titre) {
    $script:etape++
    Ecrire "[$script:etape/9] $titre"
}
function Verifier([string]$quoi) {
    if ($LASTEXITCODE -ne 0) { throw "$quoi a échoué (code $LASTEXITCODE)." }
}

try {
    Ecrire "=== Mise à jour du LIMS (base « $Base ») ==="
    if (-not (Test-Path $Python)) { throw "Environnement Python introuvable : $Python." }

    Etape "Sauvegarde de la base"
    if ($SansSauvegarde) {
        Ecrire "Sauvegarde ignorée (-SansSauvegarde) : pas de retour arrière possible pour la base."
    } else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "sauvegarde.ps1") `
            -Dossier $DossierSauvegarde -Base $Base
        Verifier "La sauvegarde"
        $derniere = Get-ChildItem -Path $DossierSauvegarde -Filter "${Base}_*.dump" | Sort-Object LastWriteTime | Select-Object -Last 1
        Ecrire "Sauvegarde : $($derniere.FullName)"
    }

    Etape "Copie de la version en place (retour arrière)"
    $copie = Join-Path $DossierVersions $Horodatage
    $exclusD = @(".venv", "node_modules", "logs", "__pycache__", "resultats", "dist")
    & robocopy $Racine $copie /E /NFL /NDL /NJH /NJS /NP /XD $exclusD /XF ".env" | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "La copie de la version en place a échoué (robocopy $LASTEXITCODE)." }
    if (Test-Path (Join-Path $Frontend "dist")) {
        & robocopy (Join-Path $Frontend "dist") (Join-Path $copie "frontend\dist") /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "La copie de frontend\dist a échoué (robocopy $LASTEXITCODE)." }
    }
    Ecrire "Version en place copiée dans $copie"

    Etape "Copie des fichiers de la nouvelle version"
    if ($Source) {
        if (-not (Test-Path $Source)) { throw "Dossier source introuvable : $Source" }
        & robocopy $Source $Racine /E /NFL /NDL /NJH /NJS /NP /XD $exclusD /XF ".env" | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "La copie de la nouvelle version a échoué (robocopy $LASTEXITCODE)." }
        Ecrire "Fichiers copiés depuis $Source"
    } else {
        Ecrire "Pas de -Source : les fichiers de la nouvelle version sont supposés déjà en place."
    }

    Etape "Arrêt du serveur"
    $tache = Get-ScheduledTask -TaskName $NomTache -ErrorAction SilentlyContinue
    if ($tache -and $tache.State -eq "Running") { Stop-ScheduledTask -TaskName $NomTache; Ecrire "Tâche « $NomTache » arrêtée." }
    $ecoute = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $ecoute) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Ecrire "Processus $($c.OwningProcess) (port $Port) arrêté."
    }
    Start-Sleep -Seconds 2

    Etape "Dépendances Python"
    & $Python -m pip install --disable-pip-version-check -q -r (Join-Path $Backend "requirements.txt")
    Verifier "pip install"

    Etape "Migrations de la base"
    Push-Location $Backend
    try { & $Python (Join-Path $PSScriptRoot "migrer.py") --base $Base; Verifier "migrer.py" } finally { Pop-Location }

    Etape "Construction de l'interface"
    Push-Location $Frontend
    try {
        & npm install --no-audit --no-fund --loglevel=error; Verifier "npm install"
        & npm run build --silent; Verifier "npm run build"
    } finally { Pop-Location }

    Etape "Redémarrage du serveur"
    if ($SansRedemarrage) {
        Ecrire "Redémarrage ignoré (-SansRedemarrage)."
    } elseif ($tache) {
        Start-ScheduledTask -TaskName $NomTache
        Ecrire "Tâche « $NomTache » démarrée."
    } else {
        # Chemin entre guillemets : Start-Process ne protège pas les espaces des arguments
        $demarrer = Join-Path $PSScriptRoot "demarrer.ps1"
        Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -WorkingDirectory $Backend -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$demarrer`"", "-Port", "$Port")
        Ecrire "Serveur lancé par demarrer.ps1 (port $Port)."
    }

    Etape "Vérification"
    if ($SansRedemarrage) {
        Ecrire "Vérification ignorée (serveur non redémarré)."
    } else {
        $sante = $null
        for ($i = 0; $i -lt 30 -and -not $sante; $i++) {
            Start-Sleep -Seconds 2
            try { $sante = Invoke-RestMethod -Uri $UrlSante -TimeoutSec 5 } catch { $sante = $null }
        }
        if (-not $sante) { throw "Le serveur ne répond pas sur $UrlSante après 60 s." }
        Ecrire ("Serveur en service : version {0}, base {1} ({2} migrations, dernière {3}), sauvegarde : {4}" -f `
            $sante.version, $sante.base.base, $sante.base.migrations, $sante.base.derniere_migration, $sante.sauvegarde.statut)
    }
    Ecrire "=== Mise à jour terminée ==="
    exit 0
}
catch {
    Ecrire "ÉCHEC à l'étape $etape : $($_.Exception.Message)"
    Ecrire "Retour arrière : docs/deploiement.md, « Retour arrière » (copie de la version : $copie ; sauvegarde de la base : $DossierSauvegarde)."
    exit 1
}
