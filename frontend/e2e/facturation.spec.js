// Facturation et paiement (bloc P) : tarifs, bulletins, encaissements.
import { expect, test } from "@playwright/test";
import { attendreMessage, capture, connexion, MOT_DE_PASSE } from "./outils.js";

test("tarifs : prix daté, historique conservé, analyses sans prix signalées", async ({ page }) => {
  await connexion(page, "admin_t");
  await page.goto("/admin/referentiels");
  await page.getByRole("tab", { name: "Tarifs des analyses" }).click();
  await expect(page.getByText("Réglages de facturation")).toBeVisible();
  await expect(page.getByText(/analyse\(s\) du catalogue sans prix en vigueur/)).toBeVisible();

  const ligne = page.locator(".ant-table-row", { hasText: "Listeria monocytogenes" });
  await expect(ligne.getByText("À valider")).toBeVisible();
  await expect(ligne.getByText(/70,00\sDH/)).toBeVisible();
  await ligne.getByRole("button", { name: "Modifier" }).click();
  const dialogue = page.getByRole("dialog");
  await dialogue.getByLabel("Prix unitaire (DH)").fill("75");
  await dialogue.getByLabel("Prix validé").click();
  await dialogue.getByRole("button", { name: "Enregistrer" }).click();
  await attendreMessage(page, "l'ancien est conservé");
  await expect(ligne.getByText(/75,00\sDH/)).toBeVisible();
  await expect(ligne.getByText("Validé")).toBeVisible();

  // Historique : deux périodes
  await ligne.locator(".ant-table-row-expand-icon").click();
  const historique = page.locator(".ant-table-expanded-row");
  await expect(historique.getByText("en vigueur")).toBeVisible();
  await expect(historique.getByText(/70,00\sDH/)).toBeVisible();
  await capture(page, "20_tarifs");
});

// Échantillon SMA dont l'analyste a saisi 2 analyses (créé par l'API)
async function echantillonAvecAnalyses(playwright, baseURL) {
  const api = await playwright.request.newContext({ baseURL });
  await api.post("/api/auth/login", { data: { username: "util1", password: MOT_DE_PASSE } });
  const r = await api.post("/api/echantillons", { data: {
    sma: "Yes", scha: "No", ssa: "No", nature: "Lait cru facturation", date_reception: "2026-10-20T09:00",
    fabricant: "Laiterie du Nord", nbre_prlvmts_sma: 2,
  } });
  expect(r.status()).toBe(201);
  const num = (await r.json()).num_echantillon;
  const a = await playwright.request.newContext({ baseURL });
  await a.post("/api/auth/login", { data: { username: "sma1", password: MOT_DE_PASSE } });
  expect((await a.post("/api/traitement/SMA", { data: { num_echantillon: num } })).status()).toBe(200);
  const res = await a.put(`/api/resultats/SMA/${num}`, { data: [
    { analyse_effectuee: "FMAT", rp1: "150", date_analyse: "2026-10-21" },
    { analyse_effectuee: "Escherichia coli", rp1: "<10", date_analyse: "2026-10-21" },
  ] });
  expect(res.status()).toBe(200);
  await api.dispose(); await a.dispose();
  return num;
}

test("lignes facturables : proposées depuis les résultats, frais divers, totaux", async ({ page, playwright, baseURL }) => {
  const num = await echantillonAvecAnalyses(playwright, baseURL);
  await connexion(page, "util1");
  await page.goto(`/echantillons/detail/${num}`);
  const bloc = page.locator(".ant-card", { has: page.getByText("Facturation", { exact: true }) });
  await expect(bloc.getByText("FMAT")).toBeVisible();
  await expect(bloc.getByText("Escherichia coli")).toBeVisible();
  await expect(bloc.locator(".ant-statistic", { hasText: "Total" })).toContainText(/120,00\sDH/);

  await bloc.getByRole("button", { name: "Frais divers" }).click();
  const dialogue = page.getByRole("dialog");
  await dialogue.getByLabel("Libellé").fill("Frais d'envoi");
  await dialogue.getByLabel("Montant unitaire (DH)").fill("15");
  await dialogue.getByRole("button", { name: "Ajouter" }).click();
  await attendreMessage(page, "Ligne ajoutée.");
  await expect(bloc.locator(".ant-statistic", { hasText: "Total" })).toContainText(/135,00\sDH/);
  await capture(page, "21_facturation_echantillon");
});

test("bulletin : brouillon, émission numérotée, avoir par un responsable", async ({ page, playwright, baseURL }) => {
  const num = await echantillonAvecAnalyses(playwright, baseURL);
  await connexion(page, "util1");
  await page.goto(`/echantillons/detail/${num}`);
  const bloc = page.locator(".ant-card", { has: page.getByText("Facturation", { exact: true }) });
  await expect(bloc.getByText("FMAT")).toBeVisible();
  await bloc.getByRole("button", { name: "Bulletin" }).click();
  const tiroir = page.locator(".ant-drawer").last();
  await expect(tiroir.getByText("Bulletin (brouillon)")).toBeVisible();
  await expect(tiroir.getByText(/120,00\sDH/).first()).toBeVisible();
  await tiroir.getByRole("button", { name: "Émettre" }).click();
  await page.locator(".ant-modal-confirm").getByRole("button", { name: "Émettre" }).click();
  await attendreMessage(page, /Bulletin BUL-\d{4}-\d{5} émis\./);
  await expect(tiroir.getByRole("button", { name: "PDF" })).toBeVisible();
  await expect(tiroir.getByText("Empreinte SHA-256")).toBeVisible();
  await capture(page, "22_bulletin_emis");
  await page.locator(".ant-drawer-close").last().click();

  // Avoir : réservé aux responsables
  await page.getByRole("button", { name: "Déconnexion" }).click();
  await connexion(page, "resp1");
  await page.goto(`/echantillons/detail/${num}`);
  await page.locator(".ant-card", { has: page.getByText("Bulletins et avoirs") }).getByRole("button", { name: /BUL-/ }).click();
  await tiroir.getByRole("button", { name: "Faire un avoir" }).click();
  const dialogue = page.getByRole("dialog", { name: /Avoir sur le bulletin/ });
  await dialogue.locator(".ant-table-row", { hasText: "FMAT" }).locator("input[type=checkbox]").check();
  await dialogue.getByLabel("Motif").fill("Analyse FMAT facturée par erreur");
  await dialogue.getByRole("button", { name: "Émettre l'avoir" }).click();
  await attendreMessage(page, /Avoir AV-\d{4}-\d{5} émis\./);
  await expect(tiroir.getByText(/Annule partiellement le bulletin/)).toBeVisible();
  await capture(page, "23_avoir");
});

// Bulletin émis par l'API pour un échantillon facturable (accueil)
async function bulletinEmis(playwright, baseURL, client, montant) {
  const api = await playwright.request.newContext({ baseURL });
  await api.post("/api/auth/login", { data: { username: "util1", password: MOT_DE_PASSE } });
  const r = await api.post("/api/echantillons", { data: {
    sma: "Yes", scha: "No", ssa: "No", nature: "Fromage", date_reception: "2026-10-22T09:00", client_nom: client,
  } });
  const num = (await r.json()).num_echantillon;
  await api.post(`/api/facturation/echantillons/${num}/lignes`, { data: { analyse: "Analyse forfaitaire", prix_unitaire: montant } });
  const f = await (await api.post("/api/facturation/factures", { data: { echantillons: [num] } })).json();
  const e = await (await api.post(`/api/facturation/factures/${f.id}/emettre`)).json();
  await api.dispose();
  return { num, numero: e.numero };
}

test("encaissements : partiel, solde, quittance, annulation par un responsable", async ({ page, playwright, baseURL }) => {
  const { num, numero } = await bulletinEmis(playwright, baseURL, "Boucherie Centrale", 150);
  await connexion(page, "util1");
  await page.goto(`/echantillons/detail/${num}`);
  await page.getByRole("button", { name: numero }).click();
  const tiroir = page.locator(".ant-drawer").last();
  await expect(tiroir.getByText("Non payé")).toBeVisible();

  await tiroir.getByRole("button", { name: "Encaisser" }).click();
  let dialogue = page.getByRole("dialog", { name: /Encaisser/ });
  await dialogue.getByLabel("Montant (DH)").fill("100");
  const quittance = page.waitForEvent("popup");
  await dialogue.getByRole("button", { name: "Enregistrer" }).click();
  await attendreMessage(page, /quittance Q-\d{4}-\d{5}/);
  await (await quittance).close();
  await expect(tiroir.getByText("Partiellement payé")).toBeVisible();

  await tiroir.getByRole("button", { name: "Encaisser" }).click();
  dialogue = page.getByRole("dialog", { name: /Encaisser/ });
  await dialogue.getByLabel("Mode").click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option", { hasText: "Chèque" }).click();
  await dialogue.getByLabel("N° de chèque").fill("0012345");
  await dialogue.getByLabel("Banque").fill("Banque Populaire");
  const quittance2 = page.waitForEvent("popup");
  await dialogue.getByRole("button", { name: "Enregistrer" }).click();
  await (await quittance2).close();
  await expect(tiroir.locator(".ant-tag", { hasText: /^Payé$/ })).toBeVisible();
  await capture(page, "24_encaissements");
  await page.locator(".ant-drawer-close").last().click();

  await page.getByRole("button", { name: "Déconnexion" }).click();
  await connexion(page, "resp1");
  await page.goto(`/echantillons/detail/${num}`);
  await page.getByRole("button", { name: numero }).click();
  await tiroir.locator(".ant-table-row", { hasText: "0012345" }).getByRole("button", { name: "Annuler" }).click();
  await page.locator(".ant-modal-confirm textarea").fill("Chèque sans provision");
  await page.locator(".ant-modal-confirm").getByRole("button", { name: "Confirmer" }).click();
  await attendreMessage(page, "Encaissement annulé.");
  await expect(tiroir.getByText("Partiellement payé")).toBeVisible();
  await expect(tiroir.locator(".ant-table-row", { hasText: "0012345" }).getByText("Annulé")).toBeVisible();
});

test("page Facturation : bulletins, impayés, journal de caisse", async ({ page, playwright, baseURL }) => {
  // Un bulletin payé en partie aujourd'hui (indépendant des autres tests)
  const { numero } = await bulletinEmis(playwright, baseURL, "Épicerie du Port", 90);
  const api = await playwright.request.newContext({ baseURL });
  await api.post("/api/auth/login", { data: { username: "util1", password: MOT_DE_PASSE } });
  const liste = await (await api.get(`/api/facturation/factures?q=${numero}`)).json();
  const id = liste.lignes[0].id;
  const jour = new Date().toISOString().slice(0, 10);
  await api.post(`/api/facturation/factures/${id}/paiements`, { data: { date_paiement: jour, montant: 30, mode: "espèces" } });
  const caisse = await (await api.get(`/api/facturation/caisse?du=${jour}&au=${jour}`)).json();
  await api.dispose();

  await connexion(page, "util1");
  await page.locator(".ant-layout-sider").getByText("Bulletins et caisse").click();
  await expect(page.getByRole("tab", { name: "Bulletins" })).toBeVisible();
  await page.getByPlaceholder("N° de bulletin ou d'échantillon").fill(numero);
  const ligne = page.locator(".ant-table-row", { hasText: numero });
  await expect(ligne.getByText("Partiellement payé")).toBeVisible();
  await expect(ligne.getByText(/60,00\sDH/)).toBeVisible();
  await capture(page, "25_facturation_bulletins");

  await page.getByRole("tab", { name: "Impayés" }).click();
  await expect(page.locator(".ant-table-row", { hasText: "Épicerie du Port" }).first()).toBeVisible();
  await capture(page, "26_facturation_impayes");

  await page.getByRole("tab", { name: "Journal de caisse" }).click();
  const total = page.locator(".ant-statistic", { hasText: `Total (${caisse.nb})` });
  const chiffres = (s) => s.replace(/[^\d,]/g, "");
  expect(chiffres(await total.innerText())).toContain(chiffres(Number(caisse.total).toFixed(2).replace(".", ",")));
  const telechargement = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Excel" }).click();
  expect((await telechargement).suggestedFilename()).toMatch(/^journal-caisse-\d{4}-\d{2}-\d{2}\.xlsx$/);
  expect(await (await telechargement).path()).toBeTruthy();   // téléchargement (Blob) terminé
  await capture(page, "27_journal_caisse");

  // Lien direct (notifications) : ouvre le bulletin
  await page.goto(`/facturation?bulletin=${id}`);
  await expect(page.locator(".ant-drawer").last().getByText(`Bulletin ${numero}`)).toBeVisible();
});

test("reporting : journal de facturation dans les requêtes enregistrées", async ({ page, playwright, baseURL }) => {
  await bulletinEmis(playwright, baseURL, "Laiterie reporting", 120);
  await connexion(page, "resp1");
  const liste = await (await page.request.get("/api/requetes/enregistrees")).json();
  const req = liste.find((r) => r.nom === "Impayés par section");
  await page.goto(`/requetes?requete=${req.id}`);
  await expect(page.getByText("Reste à recouvrer (DH)").first()).toBeVisible();
  await expect(page.getByText("Montant facturé (DH)").first()).toBeVisible();
  await expect(page.locator(".ant-table-row", { hasText: "SMA" }).first()).toBeVisible();
  await capture(page, "28_reporting_facturation");
});
