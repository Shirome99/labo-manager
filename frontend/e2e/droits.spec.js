// Un rôle de section ne voit ni les menus ni les données des autres sections (tâche 28).
// Les échantillons sont créés par l'API (compte de réception), puis l'analyste se connecte.
import { expect, test } from "@playwright/test";
import { capture, connexion, MOT_DE_PASSE } from "./outils.js";

const corps = (section) => ({
  sma: section === "SMA" ? "Yes" : "No", scha: section === "SCHA" ? "Yes" : "No", ssa: section === "SSA" ? "Yes" : "No",
  nature: `Contrôle droits ${section}`, date_reception: "2026-09-20T10:00",
});

test.beforeAll(async ({ playwright, baseURL }) => {
  const api = await playwright.request.newContext({ baseURL });
  await api.post("/api/auth/login", { data: { username: "util1", password: MOT_DE_PASSE } });
  for (const s of ["SCHA", "SSA", "SCHA"]) {
    const r = await api.post("/api/echantillons", { data: corps(s) });
    expect(r.status()).toBe(201);
  }
  await api.dispose();
});

test("analyste SMA : menus et données limités à sa section", async ({ page }) => {
  await connexion(page, "sma1");
  const menu = page.locator(".ant-layout-sider");
  await expect(menu.getByText("Microbiologie")).toBeVisible();
  await expect(menu.getByText("Chimie")).toHaveCount(0);
  await expect(menu.getByText("Santé Animale")).toHaveCount(0);
  await expect(menu.getByText("Administration")).toHaveCount(0);
  await capture(page, "15_menu_analyste_sma");

  await page.goto("/echantillons");
  await expect(page.locator(".ant-table")).toBeVisible();
  await expect(page.getByText(/Contrôle droits (SCHA|SSA)/)).toHaveCount(0);
  const sections = await page.locator(".ant-table-tbody .ant-tag").allInnerTexts();
  expect(sections.filter((t) => ["SCHA", "SSA"].includes(t.trim()))).toHaveLength(0);
  await capture(page, "16_liste_analyste_sma");

  // Accès direct à une autre section : données refusées par le serveur
  const r = await page.request.get("/api/echantillons?section=SCHA");
  expect([403, 200]).toContain(r.status());
  if (r.status() === 200) expect(await r.json()).toEqual([]);
  expect((await page.request.post("/api/requetes/executer", { data: { jeu: "echantillons", filtres: { section: ["SSA"] } } })).status()).toBe(403);
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/$/);
});

test("analyste SCHA : ne voit que la chimie", async ({ page }) => {
  await connexion(page, "scha1");
  await page.goto("/echantillons");
  await expect(page.getByText("Contrôle droits SCHA").first()).toBeVisible();
  await expect(page.getByText("Contrôle droits SSA")).toHaveCount(0);
  const menu = page.locator(".ant-layout-sider");
  await expect(menu.getByText("Microbiologie")).toHaveCount(0);
  await expect(menu.getByText("Santé Animale")).toHaveCount(0);
});
