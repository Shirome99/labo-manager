<#
.SYNOPSIS
    Lance les tests automatisés du backend (tâche 27).

.DESCRIPTION
    - supprime puis reconstruit la base de test (labo_test par défaut) par les migrations ;
    - crée les comptes de test de chaque rôle et exécute tous les tests de backend/tests ;
    - mesure la couverture du code (app/) : tableau par fichier à l'écran, rapport HTML
      dans backend/tests/resultats/couverture/ ;
    - écrit le résultat détaillé (JUnit XML) dans backend/tests/resultats/junit.xml,
      repris par le dossier de validation.
    La base de l'application (labo) n'est jamais touchée.

.PARAMETER Filtre
    Expression pytest -k pour ne lancer qu'une partie des tests (ex. "rapports").

.PARAMETER SansCouverture
    N'effectue pas la mesure de couverture (plus rapide).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File backend\scripts\tester.ps1
    powershell -ExecutionPolicy Bypass -File backend\scripts\tester.ps1 -Filtre droits
#>
param(
    [string]$Filtre = "",
    [switch]$SansCouverture
)

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$resultats = Join-Path $backend "tests\resultats"
New-Item -ItemType Directory -Force -Path $resultats | Out-Null

$python = "python"
foreach ($venv in @("venv", ".venv")) {
    $p = Join-Path $backend "$venv\Scripts\python.exe"
    if (Test-Path $p) { $python = $p; break }
}

$arguments = @("-m", "pytest", "--junitxml=$resultats\junit.xml", "-q")
if (-not $SansCouverture) {
    $arguments += @("--cov=app", "--cov-report=term", "--cov-report=html:$resultats\couverture")
}
if ($Filtre) { $arguments += @("-k", $Filtre) }

$env:PYTHONIOENCODING = "utf-8"
Push-Location $backend
try {
    & $python @arguments
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -eq 0) {
    Write-Host "Tous les tests sont passés." -ForegroundColor Green
} else {
    Write-Host "Des tests ont échoué (code $code)." -ForegroundColor Red
}
exit $code
