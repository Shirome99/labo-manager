// Finitions de l'interface (tâche 31) : version et environnement, 404, formulaire modifié, session expirée,
// états de chargement / vide / erreur, compteurs du menu, utilisation en 1366 × 768.
import { expect, test } from "@playwright/test";
import { attendreMessage, capture, connexion, MOT_DE_PASSE } from "./outils.js";

test("version, environnement de test et page 404", async ({ page }) => {
  await connexion(page, "util1");
  const version = await (await page.request.get("/api/version")).json();
  expect(version.environnement).toBe("test");
  await expect(page.locator(".shell-version")).toHaveText(`Labo Manager ${version.version} · Test`);
  await expect(page.getByText("Environnement de test : les données ne sont pas celles du laboratoire.")).toBeVisible();

  await page.goto("/adresse/inconnue");
  await expect(page.getByText("Page introuvable")).toBeVisible();
  await expect(page.getByText("/adresse/inconnue")).toBeVisible();
  await capture(page, "29_page_404");
  await page.getByRole("button", { name: "Retour à l'accueil" }).click();
  await expect(page).toHaveURL(/\/$/);
  // Une page d'administration reste réservée : retour à l'accueil, pas de 404
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/$/);
});

test("formulaire modifié : avertissement avant de quitter", async ({ page }) => {
  await connexion(page, "util1");
  await page.goto("/echantillons/ajouter");
  // Sans modification : on quitte librement
  await page.locator(".ant-layout-sider").getByText("Mon travail").click();
  await expect(page).toHaveURL(/\/travail$/);

  await page.goto("/echantillons/ajouter");
  await page.getByLabel("N° de lot").fill("LOT-NON-ENREGISTRE");
  await page.locator(".ant-layout-sider").getByText("Mon travail").click();
  const confirmation = page.locator(".ant-modal-confirm");
  await expect(page.locator(".ant-modal-confirm-title:visible")).toHaveText("Quitter sans enregistrer ?");
  await expect(page.locator(".ant-modal-confirm:visible")).toHaveCount(1);       // une seule confirmation
  await capture(page, "30_formulaire_modifie");
  await confirmation.getByRole("button", { name: "Rester sur la page" }).click();
  await expect(page).toHaveURL(/\/echantillons\/ajouter$/);
  await expect(page.getByLabel("N° de lot")).toHaveValue("LOT-NON-ENREGISTRE");

  await page.locator(".ant-layout-sider").getByText("Mon travail").click();
  await page.locator(".ant-modal-confirm").getByRole("button", { name: "Quitter sans enregistrer" }).click();
  await expect(page).toHaveURL(/\/travail$/);
});

test("session expirée : message, puis retour à la page demandée", async ({ page }) => {
  await connexion(page, "util1");
  await page.goto("/echantillons?statut=Re%C3%A7u");
  await expect(page.locator(".ant-table")).toBeVisible();
  // La session est fermée côté serveur (équivalent d'une expiration)
  await page.request.post("/api/auth/logout");
  await page.locator(".ant-layout-sider").getByText("Mon travail").click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText(/Session expirée/)).toBeVisible();
  await capture(page, "31_session_expiree");
  await page.getByLabel("Utilisateur").fill("util1");
  await page.getByLabel("Mot de passe").fill(MOT_DE_PASSE);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/travail$/);
  await expect(page.getByText("Mon travail").first()).toBeVisible();
});

test("états d'erreur (Réessayer) et état vide avec action", async ({ page }) => {
  await connexion(page, "resp1");
  let echec = true;
  await page.route("**/api/travail", (route) => (echec
    ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Erreur simulée pour le test." }) })
    : route.continue()));
  await page.goto("/travail");
  await expect(page.getByText("Erreur simulée pour le test.")).toBeVisible();
  await capture(page, "32_erreur_reessayer");
  echec = false;
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(page.getByText("Erreur simulée pour le test.")).toHaveCount(0);
  await expect(page.locator(".ant-table")).toBeVisible();

  await page.route("**/api/reactifs?*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/reactifs", (route) => (route.request().method() === "GET"
    ? route.fulfill({ status: 200, contentType: "application/json", body: "[]" }) : route.continue()));
  await page.goto("/reactifs");
  await expect(page.getByText("Aucun lot enregistré.")).toBeVisible();
  await expect(page.locator(".ant-empty").getByRole("button", { name: "Nouveau lot" })).toBeVisible();
});

test("compteurs à 5 chiffres du menu et largeur 1366 × 768", async ({ page }) => {
  await page.route("**/api/echantillons/stats", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ total: 21946, totalSMA: 10946, totalSCHA: 6584, totalSSA: 4416 }),
  }));
  await connexion(page, "admin_t");
  const titre = page.locator(".ant-menu-submenu-title", { hasText: "Microbiologie" });
  const compteur = titre.locator(".menu-count");
  await expect(compteur).toHaveText("10,9 k");
  await expect(compteur).toHaveAttribute("title", /10\s946/);
  const fleche = await titre.locator(".ant-menu-submenu-arrow").boundingBox();
  const boite = await compteur.boundingBox();
  expect(boite.x + boite.width).toBeLessThanOrEqual(fleche.x);       // le compteur ne chevauche pas la flèche
  await capture(page, "33_menu_compteurs");

  // Pas de défilement horizontal de la page sur les écrans principaux (1366 × 768)
  for (const url of ["/", "/echantillons", "/echantillons/ajouter", "/travail", "/requetes", "/bilan-mensuel",
                     "/facturation", "/admin/referentiels", "/traitement/SMA", "/resultats/SCHA"]) {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    const deborde = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(deborde, `défilement horizontal sur ${url}`).toBeLessThanOrEqual(0);
  }
});
