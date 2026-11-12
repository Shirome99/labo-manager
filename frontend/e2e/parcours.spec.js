// Parcours complet d'un échantillon SMA, de la réception au bilan mensuel (tâche 28).
// Les étapes s'enchaînent sur la même base de test ; chaque étape produit une capture
// d'écran dans docs/captures/ (reprises par le guide utilisateur).
import { expect, test } from "@playwright/test";
import { attendreMessage, capture, choisir, connexion, saisirDate } from "./outils.js";

test.describe.configure({ mode: "serial" });

const annee = new Date().getFullYear();
let num;   // n° généré à la réception, repris par les étapes suivantes

test("connexion", async ({ page }) => {
  await page.goto("/login");
  await capture(page, "01_connexion");
  await page.getByLabel("Utilisateur").fill("util1");
  await page.getByLabel("Mot de passe").fill("mauvais");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByText("Identifiants incorrects")).toBeVisible();
  await connexion(page, "util1");
  await capture(page, "02_tableau_de_bord");
});

test("réception d'un échantillon : cascade type → sous-type, section unique, numéro généré", async ({ page }) => {
  await connexion(page, "util1");
  await page.goto("/echantillons/ajouter");
  await expect(page.getByText("Identification")).toBeVisible();

  // Section obligatoire : enregistrement refusé sans section
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Choisissez la section de l'échantillon")).toBeVisible();

  await saisirDate(page, "Date de réception", `15/09/${annee} 09:30`);
  await choisir(page, "Nature de l'échantillon", "Beurre pasteurisé");
  // Cascade : sous-type désactivé tant qu'aucun type n'est choisi, puis filtré par le type
  const sousType = page.getByLabel("Sous-type d'échantillon", { exact: true });
  await expect(sousType).toBeDisabled();
  await choisir(page, "Type d'échantillon", "Laits et Produits laitiers");
  await expect(sousType).toBeEnabled();
  await sousType.click();
  const options = page.locator(".ant-select-dropdown:visible .ant-select-item-option");
  await expect(options).toHaveCount(8);
  await options.first().click();

  await page.getByRole("radio", { name: /Microbiologie/ }).check();
  await capture(page, "03_reception_formulaire");
  // Numéro attendu : le suivant de la séquence SMA de l'année (d'autres fichiers de tests ont pu en créer)
  const existants = await (await page.request.get(`/api/echantillons?section=SMA&q=${annee}-SMA-&page=1&taille=500`)).json();
  const dernier = Math.max(0, ...existants.lignes.map((e) => Number(e.num_echantillon.match(/-(\d{4})$/)?.[1] || 0)));
  const attendu = `${annee}-SMA-${String(dernier + 1).padStart(4, "0")}`;
  await page.getByRole("button", { name: "Enregistrer" }).click();

  const modale = page.locator(".ant-modal").filter({ hasText: "enregistré" });
  await expect(modale).toBeVisible();
  const texte = await modale.innerText();
  num = texte.match(new RegExp(`${annee}-SMA-\\d{4}`))[0];
  expect(num).toBe(attendu);
  await capture(page, "04_reception_numero_genere");
  await modale.getByRole("button", { name: "Retour à la liste" }).click();
  await expect(page.getByRole("cell", { name: num })).toBeVisible();
});

test("saisie de la fiche de traitement et des résultats, soumission (analyste SMA)", async ({ page }) => {
  await connexion(page, "sma1");
  await page.goto(`/traitement/SMA?num=${num}`);
  await saisirDate(page, "Date mise en analyse", `16/09/${annee}`);
  await page.getByRole("button", { name: "Enregistrer la fiche" }).click();
  await expect(page.getByRole("button", { name: "Mettre à jour" })).toBeVisible();
  await capture(page, "05_traitement_fiche");

  await page.goto(`/resultats/SMA?num=${num}`);
  // Une carte « Analyse 1 » vide est proposée d'office
  const carte = page.locator(".ant-card").filter({ hasText: /^Analyse 1/i }).first();
  await carte.getByRole("combobox").first().fill("Escherichia coli");
  await page.keyboard.press("Escape");
  const rps = carte.locator("input.res-rp-input");
  for (const [i, v] of ["<10", "<10", "15", "<10", "<10"].entries()) await rps.nth(i).fill(v);
  await page.getByRole("button", { name: "Enregistrer les résultats" }).click();
  await attendreMessage(page, "analyse(s) enregistrée(s)");
  await capture(page, "06_resultats_saisis");

  await page.goto(`/traitement/SMA?num=${num}`);
  await page.getByRole("button", { name: "Soumettre à validation" }).click();
  await expect(page.getByText("Fiche verrouillée")).toBeVisible();
  await capture(page, "07_fiche_soumise");
});

test("validation par un autre compte et émission du rapport (responsable)", async ({ page, context }) => {
  await connexion(page, "resp1");
  await page.goto(`/traitement/SMA?num=${num}`);
  await page.getByRole("button", { name: "Valider (double regard)" }).click();
  await expect(page.getByRole("button", { name: "Valider (double regard)" })).toHaveCount(0);
  await capture(page, "08_fiche_validee");

  await page.goto(`/echantillons/detail/${num}`);
  await expect(page.getByRole("button", { name: "Rapport d'essai PDF" })).toBeVisible();
  await expect(page.locator(".ant-tag", { hasText: "Validé" }).first()).toBeVisible();
  await capture(page, "09_detail_pret_rapport");
  const [pdf] = await Promise.all([
    context.waitForEvent("page"),
    page.getByRole("button", { name: "Rapport d'essai PDF" }).click(),
  ]);
  // 1re ouverture du PDF = émission officielle (nouvel onglet)
  await pdf.waitForLoadState("load", { timeout: 15000 }).catch(() => {});
  await pdf.close();
  await page.reload();
  await expect(page.getByRole("button", { name: new RegExp(`Rapport \\d{4}/MA/${annee}`) })).toBeVisible();
  await expect(page.getByText("Rapports d'essai émis")).toBeVisible();
  await capture(page, "10_rapport_emis");
  // Le rapport figé est servi à l'identique
  const r1 = await page.request.get(`/api/rapports/SMA/${num}`);
  const r2 = await page.request.get(`/api/rapports/SMA/${num}`);
  expect(r1.headers()["x-rapport-sha256"]).toBe(r2.headers()["x-rapport-sha256"]);
  expect(r1.status()).toBe(200);
});

test("liste et export Excel", async ({ page }) => {
  await connexion(page, "util1");
  await page.goto("/echantillons");
  await expect(page.getByRole("cell", { name: num })).toBeVisible();
  await capture(page, "11_liste_echantillons");
  const [telechargement] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /Excel/ }).click(),
  ]);
  expect(telechargement.suggestedFilename()).toMatch(/^echantillons_.*\.xlsx$/);
  // Téléchargement terminé avant la fin du test (fichier produit par un Blob : Edge ne doit pas fermer en cours)
  expect(await telechargement.path()).toBeTruthy();
});

test("requête et bilan mensuel", async ({ page }) => {
  await connexion(page, "resp1");
  await page.goto("/requetes");
  // Requête par section, sur l'année en cours (réception du parcours le 15/09) : indépendant de la date
  await page.getByText("Mois précédent", { exact: true }).click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option", { hasText: "Année en cours" }).click();
  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.locator(".ant-table-row").filter({ hasText: "SMA" }).first()).toBeVisible();
  await capture(page, "12_requete_resultat");

  await page.goto("/bilan-mensuel");
  await page.getByRole("button", { name: "Aperçu" }).click();
  await expect(page.getByText("Échantillons reçus").first()).toBeVisible();
  await capture(page, "13_bilan_apercu");
  const [bilan] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Générer PDF" }).click(),
  ]);
  expect(bilan.suggestedFilename()).toMatch(/\.pdf$/);
  await expect(page.getByText("Bilans archivés")).toBeVisible();
  await capture(page, "14_bilan_archive");
});
