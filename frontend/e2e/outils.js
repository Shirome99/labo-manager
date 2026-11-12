// Aides communes aux tests de bout en bout.
import { expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

export const MOT_DE_PASSE = "Testlims2026";
export const CAPTURES = path.resolve(import.meta.dirname, "..", "..", "docs", "captures");
fs.mkdirSync(CAPTURES, { recursive: true });

/** Connexion par l'écran de connexion. */
export async function connexion(page, nom) {
  await page.goto("/login");
  await page.getByLabel("Utilisateur").fill(nom);
  await page.getByLabel("Mot de passe").fill(MOT_DE_PASSE);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByText("Tableau de bord").first()).toBeVisible();
}

/** Capture d'écran pour le guide utilisateur (docs/captures/<nom>.png). */
export async function capture(page, nom) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.screenshot({ path: path.join(CAPTURES, `${nom}.png`) });
}

/** Choix dans un Select / AutoComplete antd repéré par le libellé de son Form.Item. */
export async function choisir(page, libelle, texte, { exact = false } = {}) {
  const champ = page.getByLabel(libelle, { exact: true });
  await champ.click();
  await champ.fill(texte);
  const option = page.locator(".ant-select-dropdown:visible .ant-select-item-option", { hasText: texte }).first();
  await option.click();
  if (exact) await expect(page.locator(".ant-select-dropdown:visible")).toHaveCount(0);
}

/** Saisie d'une date dans un DatePicker antd repéré par son libellé. */
export async function saisirDate(page, libelle, valeur) {
  const champ = page.getByLabel(libelle, { exact: true });
  await champ.click();
  await champ.fill(valeur);
  await champ.press("Enter");
}

/** Message de retour antd (message.success / error). */
export async function attendreMessage(page, texte) {
  await expect(page.locator(".ant-message").getByText(texte).first()).toBeVisible();
}
