<#
.SYNOPSIS
    Sauvegarde horodatée de la base PostgreSQL « labo » (LIMS LRARVY).

.DESCRIPTION
    - pg_dump au format « custom » (-Fc), restaurable avec pg_restore ;
    - fichier nommé <Base>_AAAA-MM-JJ_HHmmss.dump dans le dossier choisi ;
    - suppression des sauvegardes de plus de N jours (30 par défaut),
      uniquement les fichiers <Base>_*.dump de ce dossier ;
    - journal : sauvegarde.log dans le même dossier.

    Mot de passe : jamais dans ce script. Utiliser le fichier
    %APPDATA%\postgresql\pgpass.conf (recommandé, voir docs/sauvegarde.md)
    ou la variable d'environnement PGPASSWORD.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File backend\scripts\sauvegarde.ps1 -Dossier "D:\Sauvegardes\labo"
#>
[CmdletBinding()]
param(
    [string]$Dossier = $(if ($env:LIMS_SAUVEGARDE_DIR) { $env:LIMS_SAUVEGARDE_DIR } else { "D:\Sauvegardes\labo" }),
    [string]$Base = "labo",
    [string]$Hote = "localhost",
    [int]$Port = 5432,
    [string]$Utilisateur = "postgres",
    [ValidateRange(1, 3650)]
    [int]$RetentionJours = 30,
    [string]$PgBin = ""
)

$ErrorActionPreference = "Stop"

function Ecrire-Journal([string]$message) {
    $ligne = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Write-Output $ligne
    Add-Content -Path (Join-Path $Dossier "sauvegarde.log") -Value $ligne -Encoding UTF8
}

# ---- Localiser pg_dump (paramètre, PATH, puis installations standard) ----
function Trouver-PgDump {
    if ($PgBin) {
        $p = Join-Path $PgBin "pg_dump.exe"
        if (Test-Path $p) { return $p }
        throw "pg_dump.exe introuvable dans $PgBin"
    }
    $cmd = Get-Command pg_dump.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidats = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Directory.Parent.Name -replace '\D', '') } -Descending
    if ($candidats) { return $candidats[0].FullName }
    throw "pg_dump.exe introuvable : installez les outils PostgreSQL ou passez -PgBin."
}

if (-not (Test-Path $Dossier)) {
    New-Item -ItemType Directory -Path $Dossier | Out-Null
}

try {
    $pgDump = Trouver-PgDump
    $horodatage = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $fichier = Join-Path $Dossier ("{0}_{1}.dump" -f $Base, $horodatage)

    Ecrire-Journal "Début de la sauvegarde de « $Base » vers $fichier"
    & $pgDump --host=$Hote --port=$Port --username=$Utilisateur --no-password `
        --format=custom --compress=6 --file=$fichier $Base
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $fichier) { Remove-Item $fichier -Force }
        throw "pg_dump a échoué (code $LASTEXITCODE). Vérifiez le mot de passe (pgpass.conf) et l'accès au serveur."
    }
    $taille = [math]::Round((Get-Item $fichier).Length / 1KB, 1)
    Ecrire-Journal "Sauvegarde terminée : $fichier ($taille Ko)"

    # ---- Rétention : seuls les fichiers <Base>_*.dump de ce dossier ----
    $limite = (Get-Date).AddDays(-$RetentionJours)
    $anciens = Get-ChildItem -Path $Dossier -Filter ("{0}_*.dump" -f $Base) -File |
        Where-Object { $_.LastWriteTime -lt $limite }
    foreach ($f in $anciens) {
        Remove-Item $f.FullName -Force
        Ecrire-Journal "Supprimée (plus de $RetentionJours jours) : $($f.Name)"
    }
    exit 0
}
catch {
    Ecrire-Journal "ERREUR : $($_.Exception.Message)"
    exit 1
}
