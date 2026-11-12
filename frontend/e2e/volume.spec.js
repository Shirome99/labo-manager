// Interface sur un volume réaliste (tâche 30) : pagination, tri et compteurs côté serveur.
// Lancement : E2E_VOLUME=22000 npx playwright test volume   (base remplie par remplir_volume.py)
import { expect, test } from "@playwright/test";
import { capture, connexion } from "./outils.js";

test.skip(!process.env.E2E_VOLUME, "Test de volume : définir E2E_VOLUME (ex. 22000).");

test("liste de plus de 20 000 échantillons : pages, tri, compteurs", async ({ page }) => {
  await connexion(page, "util1");
  const debut = Date.now();
  await page.goto("/echantillons");
  await expect(page.locator(".ant-table-tbody tr.ant-table-row")).toHaveCount(50);
  const duree = Date.now() - debut;
  expect(duree).toBeLessThan(3000);
  const total = Number((await page.getByText(/^\d+ échantillons$/).first().innerText()).split(" ")[0]);
  expect(total).toBeGreaterThanOrEqual(20000);
  await capture(page, "18_liste_volume");

  // Page suivante : 50 autres lignes
  const premiere = await page.locator(".ant-table-tbody tr.ant-table-row").first().innerText();
  await page.locator(".ant-pagination-next").click();
  await expect(page.locator(".ant-pagination-item-active")).toHaveText("2");
  await expect(page.locator(".ant-table-tbody tr.ant-table-row").first()).not.toHaveText(premiere);

  // Tri par date de réception croissante : retour en page 1, le plus ancien en tête
  await page.getByRole("columnheader", { name: "Réception" }).click();
  await expect(page.locator(".ant-pagination-item-active")).toHaveText("1");
  const dates = await page.locator(".ant-table-tbody .cell-date").allInnerTexts();
  const lues = dates.filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
  expect([...lues].sort()).toEqual(lues);

  // Filtre statut : le total affiché est le compteur du statut
  const option = page.locator(".filtre-statuts .ant-segmented-item", { hasText: "À valider" });
  const attendu = Number((await option.innerText()).match(/\((\d+)\)/)[1]);
  await option.click();
  await expect(page.getByText(new RegExp(`^${attendu} échantillons?$`)).first()).toBeVisible();
});

test("sélecteur d'échantillon : recherche côté serveur", async ({ page }) => {
  await connexion(page, "sma1");
  await page.goto("/traitement/SMA");
  const champ = page.getByRole("combobox").first();
  await champ.click();
  await champ.fill("2024-SMA-012");
  const options = page.locator(".ant-select-dropdown:visible .ant-select-item-option");
  await expect(options.first()).toContainText("2024-SMA-012");
  expect(await options.count()).toBeGreaterThan(0);
  await options.first().click();
  await expect(page.getByText(/File de travail|Fiche/).first()).toBeVisible();
  await capture(page, "19_selecteur_echantillon");
});
