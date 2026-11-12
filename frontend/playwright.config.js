// Tests de bout en bout de l'interface (tâche 28).
// Le serveur de test (backend/scripts/serveur_test.py) reconstruit la base labo_test,
// crée les comptes de test et sert le front construit (npm run build) sur le port 8020.
// Lancement : npm run e2e   (build puis npx playwright test)
import { defineConfig } from "@playwright/test";
import path from "node:path";

const backend = path.resolve(import.meta.dirname, "..", "backend");
const python = path.join(backend, ".venv", "Scripts", "python.exe");
const PORT = Number(process.env.E2E_PORT || 8020);

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e/resultats",
  fullyParallel: false,
  workers: 1,                      // un seul parcours, dans l'ordre, sur une même base
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["junit", { outputFile: "e2e/resultats/junit.xml" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Edge installé sur les postes Windows du labo ; PW_CHANNEL=chromium pour le navigateur de Playwright
    channel: process.env.PW_CHANNEL || "msedge",
    viewport: { width: 1366, height: 768 },   // écran courant au labo
    locale: "fr-FR",
    timezoneId: "Africa/Casablanca",
    acceptDownloads: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    // E2E_VOLUME=22000 : base remplie d'un volume réaliste (tests de volume/*.spec.js)
    command: `"${python}" scripts/serveur_test.py --port ${PORT}` + (process.env.E2E_VOLUME ? ` --volume ${process.env.E2E_VOLUME}` : ""),
    cwd: backend,
    url: `http://127.0.0.1:${PORT}/api/health`,
    timeout: 120_000,
    reuseExistingServer: false,
    stdout: "pipe",
    env: { PYTHONIOENCODING: "utf-8" },
  },
});
