// Erreur serveur provoquée volontairement : message propre à l'écran, ligne dans le journal (tâche 29).
// Le serveur de test expose /api/test/erreur (environnement de test seulement) ; on y redirige
// le chargement de la liste des échantillons.
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { capture, connexion } from "./outils.js";

const JOURNAL = path.resolve(import.meta.dirname, "..", "..", "backend", "tests", "resultats", "logs", "lims.log");

test("erreur inattendue : message avec référence, trace dans le journal", async ({ page, baseURL }) => {
  await connexion(page, "util1");
  await page.route(/\/api\/echantillons(\?.*)?$/, (route) => route.continue({ url: `${baseURL}/api/test/erreur` }));
  await page.goto("/echantillons");
  const alerte = page.locator(".ant-alert-error");
  await expect(alerte).toContainText("Erreur interne du serveur (référence");
  await expect(alerte).not.toContainText("Traceback");
  await capture(page, "17_erreur_serveur");
  const ref = (await alerte.innerText()).match(/référence ([0-9A-F]{8})/)[1];
  await expect.poll(() => fs.readFileSync(JOURNAL, "utf-8")).toContain(`[ref ${ref}] GET /api/test/erreur (utilisateur util1)`);
  expect(fs.readFileSync(JOURNAL, "utf-8")).toContain("RuntimeError: Erreur provoquée volontairement");
});
