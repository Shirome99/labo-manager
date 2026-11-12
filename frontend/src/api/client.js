// API : même origine en local (proxy Vite, ou build servi par FastAPI) ; en démonstration en ligne
// (front GitHub Pages), VITE_API_URL = adresse de l'API Render
const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
const BASE = API_URL + "/api";
// API sur un autre site : le cookie de session serait un cookie tiers (bloqué par Brave, Safari),
// l'authentification passe par un jeton « Authorization: Bearer » (sessionStorage)
const DISTANT = API_URL !== "";
const CLE_JETON = "lims.jeton";
// Appels qui ne prolongent pas la session (comme côté serveur) ou qui gèrent eux-mêmes le jeton
const SANS_RENOUVELLEMENT = new Set(["/notifications", "/auth/login", "/auth/renouveler", "/auth/logout", "/version"]);

function lireJeton() {
  try { return JSON.parse(sessionStorage.getItem(CLE_JETON) || "null"); } catch { return null; }
}
function garderJeton(jeton, duree) {
  try { sessionStorage.setItem(CLE_JETON, JSON.stringify({ jeton, duree, emis: Date.now() })); } catch { /* navigation privée */ }
}
function effacerJeton() {
  try { sessionStorage.removeItem(CLE_JETON); } catch { /* ignore */ }
}

function entetes(json = true) {
  const h = json ? { "Content-Type": "application/json" } : {};
  const j = DISTANT && lireJeton();
  if (j?.jeton) h.Authorization = `Bearer ${j.jeton}`;
  return h;
}

// Renouvellement du jeton pendant l'activité, à mi-durée (un seul appel à la fois)
let renouvellement = null;
async function renouvelerSiBesoin(path) {
  const j = DISTANT && lireJeton();
  if (!j?.jeton || SANS_RENOUVELLEMENT.has(path) || Date.now() - j.emis < (j.duree * 1000) / 2) return;
  renouvellement ??= fetch(BASE + "/auth/renouveler", { method: "POST", headers: entetes(), credentials: "include" })
    .then(async (r) => {
      if (r.ok) { const d = await r.json(); garderJeton(d.jeton, d.jeton_duree); } else if (r.status === 401) effacerJeton();
    })
    .catch(() => { /* réseau : l'appel suivant dira ce qu'il en est */ })
    .finally(() => { renouvellement = null; });
  await renouvellement;
}

// Réveil du serveur : l'API gratuite de Render s'endort ; si le 1er appel dépasse 3 s, la page
// affiche « Démarrage du serveur, merci de patienter… » (événement lims:reveil)
let premierAppel = true;
async function appeler(url, options) {
  if (!premierAppel) return fetch(url, options);
  premierAppel = false;
  const minuterie = setTimeout(() => window.dispatchEvent(new CustomEvent("lims:reveil", { detail: true })), 3000);
  try { return await fetch(url, options); } finally {
    clearTimeout(minuterie);
    window.dispatchEvent(new CustomEvent("lims:reveil", { detail: false }));
  }
}

function signaler401(res, path) {
  if (res.status !== 401 || path === "/auth/login") return;
  effacerJeton();
  // Session expirée (inactivité, durée maximale) : l'application revient à la connexion
  window.dispatchEvent(new CustomEvent("lims:session-expiree"));
}

async function request(path, options = {}) {
  await renouvelerSiBesoin(path);
  const res = await appeler(BASE + path, {
    credentials: "include", // envoie le cookie de session (serveur local)
    ...options,
    headers: entetes(),
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (res.status === 204) {
    if (path === "/auth/logout") effacerJeton();
    return null;
  }
  signaler401(res, path);

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(messageErreur(res, data));
  if (path === "/auth/login" && data.jeton) {
    if (DISTANT) garderJeton(data.jeton, data.jeton_duree);
    delete data.jeton;
  }
  return data;
}

// Message d'erreur affichable : le serveur renvoie toujours {detail} en français
// (avec une référence pour une erreur inattendue) ; repli si la réponse n'est pas du JSON.
function messageErreur(res, data) {
  if (typeof data.detail === "string" && data.detail) return data.detail;
  if (Array.isArray(data.detail)) return "Données invalides : " + data.detail.map((e) => e.msg || e.message).join(" ; ");
  if (res.status >= 500) return `Erreur du serveur (${res.status}). Réessayez ; si le problème persiste, prévenez l'administrateur.`;
  return `Erreur ${res.status}`;
}

// Réponse d'un fichier (PDF, Excel, CSV) -> Blob + nom (en-tête Content-Disposition)
async function lireFichier(res, path, nomDefaut) {
  signaler401(res, path);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(messageErreur(res, data));
  }
  const cd = res.headers.get("Content-Disposition") || "";
  const nom = /filename\*=UTF-8''([^;]+)/i.exec(cd)?.[1] || /filename="?([^";]+)"?/i.exec(cd)?.[1] || nomDefaut;
  return { blob: await res.blob(), nom: decodeURIComponent(nom) };
}

function enregistrerBlob(blob, nom) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: nom });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// Téléchargement d'un fichier produit par un POST (exports du reporting)
async function telecharger(path, body, nomDefaut) {
  await renouvelerSiBesoin(path);
  const res = await appeler(BASE + path, {
    method: "POST", credentials: "include", headers: entetes(), body: JSON.stringify(body),
  });
  const { blob, nom } = await lireFichier(res, path, nomDefaut);
  enregistrerBlob(blob, nom);
}

// Fichier d'une URL de l'API (rapport, bulletin, quittance, étiquettes, bilan, export) : récupéré par
// fetch (avec le jeton : un lien direct ne le transporterait pas), puis ouvert dans un onglet (PDF)
// ou téléchargé. L'onglet est ouvert tout de suite (pendant le clic) pour ne pas être bloqué.
async function ouvrirFichier(url, { telecharger: aTelecharger = false, nom = "fichier" } = {}) {
  const onglet = aTelecharger ? null : window.open("", "_blank");
  try {
    const path = url.startsWith(BASE) ? url.slice(BASE.length).split("?")[0] : url;
    await renouvelerSiBesoin(path);
    const res = await appeler(url, { credentials: "include", headers: entetes(false) });
    const { blob, nom: nomFichier } = await lireFichier(res, path, nom);
    if (aTelecharger || !onglet || blob.type !== "application/pdf") {
      onglet?.close();
      enregistrerBlob(blob, nomFichier);
      return;
    }
    const lien = URL.createObjectURL(blob);
    onglet.location.href = lien;
    setTimeout(() => URL.revokeObjectURL(lien), 60000);
  } catch (e) {
    onglet?.close();
    throw e;
  }
}

export const api = {
  // Fichiers de l'API (PDF, Excel, CSV) : jamais de lien direct, voir ouvrirFichier
  ouvrirFichier,
  // Auth
  login: (username, password) =>
    request("/auth/login", { method: "POST", body: { username, password } }),
  logout: () => request("/auth/logout", { method: "POST" }),
  me: () => request("/auth/me"),
  version: () => request("/version"),
  changerMotDePasse: (actuel, nouveau) =>
    request("/auth/mot-de-passe", { method: "POST", body: { actuel, nouveau } }),

  // Équipements et étalonnage (tâche 17)
  equipements: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    return request(`/equipements${qs ? "?" + qs : ""}`);
  },
  creerEquipement: (body) => request("/equipements", { method: "POST", body }),
  modifierEquipement: (id, body) => request(`/equipements/${id}`, { method: "PATCH", body }),
  supprimerEquipement: (id) => request(`/equipements/${id}`, { method: "DELETE" }),
  evenementsEquipement: (id) => request(`/equipements/${id}/evenements`),
  ajouterEvenementEquipement: (id, body) => request(`/equipements/${id}/evenements`, { method: "POST", body }),

  // Réactifs et milieux de culture (tâche 20)
  reactifs: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    return request(`/reactifs${qs ? "?" + qs : ""}`);
  },
  creerLotReactif: (body) => request("/reactifs", { method: "POST", body }),
  modifierLotReactif: (id, body) => request(`/reactifs/${id}`, { method: "PATCH", body }),
  supprimerLotReactif: (id) => request(`/reactifs/${id}`, { method: "DELETE" }),
  mouvementsReactif: (id) => request(`/reactifs/${id}/mouvements`),
  ajouterMouvementReactif: (id, body) => request(`/reactifs/${id}/mouvements`, { method: "POST", body }),
  utilisationsReactif: (id) => request(`/reactifs/${id}/utilisations`),
  tracabiliteReactifs: (num) => request(`/reactifs/echantillon/${encodeURIComponent(num)}`),

  // Contrôles qualité internes (tâche 18)
  seriesCQ: () => request("/cq/series"),
  serieCQ: (id) => request(`/cq/series/${id}`),
  creerSerieCQ: (body) => request("/cq/series", { method: "POST", body }),
  modifierSerieCQ: (id, body) => request(`/cq/series/${id}`, { method: "PATCH", body }),
  ajouterMesureCQ: (id, body) => request(`/cq/series/${id}/mesures`, { method: "POST", body }),

  // Habilitations du personnel (tâche 19)
  habilitations: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    return request(`/habilitations${qs ? "?" + qs : ""}`);
  },
  utilisateursHabilitables: () => request("/habilitations/utilisateurs"),
  creerHabilitation: (body) => request("/habilitations", { method: "POST", body }),
  modifierHabilitation: (id, body) => request(`/habilitations/${id}`, { method: "PATCH", body }),
  supprimerHabilitation: (id) => request(`/habilitations/${id}`, { method: "DELETE" }),

  // Reporting : moteur de requêtes (catalogue fermé, aucun SQL libre)
  catalogueRequetes: () => request("/requetes/catalogue"),
  executerRequete: (definition) => request("/requetes/executer", { method: "POST", body: definition }),
  // Détail paginé côté serveur : {colonnes, lignes, total, page, taille}
  detailRequete: (definition, valeurs, page = 1, taille = 50) =>
    request("/requetes/detail", { method: "POST", body: { definition, valeurs, page, taille } }),
  valeursRequete: (jeu, dimension, filtres = {}) =>
    request(`/requetes/valeurs?dimension=${encodeURIComponent(dimension)}`, { method: "POST", body: { jeu, filtres } }),
  requetesEnregistrees: () => request("/requetes/enregistrees"),
  requeteEnregistree: (id) => request(`/requetes/enregistrees/${id}`),
  creerRequeteEnregistree: (body) => request("/requetes/enregistrees", { method: "POST", body }),
  modifierRequeteEnregistree: (id, body) => request(`/requetes/enregistrees/${id}`, { method: "PATCH", body }),
  supprimerRequeteEnregistree: (id) => request(`/requetes/enregistrees/${id}`, { method: "DELETE" }),
  // Bilan mensuel (archivé à chaque génération)
  genererBilan: (mois, section, format) =>
    telecharger("/bilans/generer", { mois, section: section || null, format }, `bilan_${mois}.${format}`),
  apercuBilan: (mois, section) => request("/bilans/apercu", { method: "POST", body: { mois, section: section || null } }),
  historiqueBilans: (mois) => request(`/bilans/historique${mois ? "?mois=" + mois : ""}`),
  urlBilan: (id) => `${BASE}/bilans/fichier/${id}`,
  modeleBilan: () => request("/bilans/modele"),
  enregistrerModeleBilan: (blocs) => request("/bilans/modele", { method: "PUT", body: blocs }),
  exporterRequete: (definition, titre, format) =>
    telecharger(`/requetes/export?format=${format}`, { definition, titre }, `requete.${format}`),

  // File de travail selon le rôle (page « Mon travail », Précédent / Suivant)
  travail: () => request("/travail"),

  // Notifications de la topbar (à valider, fiches renvoyées, retards)
  notifications: () => request("/notifications"),

  // Échantillons
  echantillons: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v)
    ).toString();
    return request(`/echantillons${qs ? "?" + qs : ""}`);
  },
  // Export Excel/CSV : URL directe (téléchargement), mêmes filtres que la liste
  urlExportEchantillons: (params = {}, format = "xlsx") => {
    const qs = new URLSearchParams(
      Object.entries({ ...params, format }).filter(([, v]) => v)
    ).toString();
    return `${BASE}/echantillons/export?${qs}`;
  },
  stats: () => request("/echantillons/stats"),
  // Étiquettes PDF (Code 128) : une par prélèvement ; format en mm facultatif
  urlEtiquettes: (num, largeur, hauteur) => {
    const qs = new URLSearchParams(Object.entries({ largeur, hauteur }).filter(([, v]) => v)).toString();
    return `${BASE}/echantillons/${encodeURIComponent(num)}/etiquette${qs ? "?" + qs : ""}`;
  },
  dashboard: () => request("/echantillons/dashboard"),
  echantillon: (num) => request(`/echantillons/${encodeURIComponent(num)}`),
  echantillonComplet: (num) => request(`/echantillons/${encodeURIComponent(num)}/complet`),
  changerStatut: (num, statut) =>
    request(`/echantillons/${encodeURIComponent(num)}/statut`, { method: "PATCH", body: { statut } }),

  // Rapport d'essai : URL directe (le PDF s'ouvre dans un nouvel onglet)
  urlRapport: (section, num) =>
    `${BASE}/rapports/${section}/${encodeURIComponent(num)}`,
  // Rapports émis (figés) : historique des versions, PDF d'une version, erratum
  rapportsHistorique: (num) => request(`/rapports/historique/${encodeURIComponent(num)}`),
  urlRapportVersion: (id) => `${BASE}/rapports/fichier/${id}`,
  erratumRapport: (section, num, motif) =>
    request(`/rapports/${section}/${encodeURIComponent(num)}/erratum`, { method: "POST", body: { motif } }),

  // Référentiels (lecture, formulaires)
  categoriesRef: (q) => request(`/ref/categories${q ? "?q=" + encodeURIComponent(q) : ""}`),
  analysesRef: (section, q) =>
    request(`/ref/analyses?section=${section}${q ? "&q=" + encodeURIComponent(q) : ""}`),
  criteresRef: (categorie) =>
    request(`/ref/criteres?categorie=${encodeURIComponent(categorie)}`),
  naturesRef: (q) => request(`/ref/natures${q ? "?q=" + encodeURIComponent(q) : ""}`),
  fabricantsRef: (q) => request(`/ref/fabricants${q ? "?q=" + encodeURIComponent(q) : ""}`),
  organismesRef: (q) => request(`/ref/organismes${q ? "?q=" + encodeURIComponent(q) : ""}`),
  typesEchantillonRef: () => request(`/ref/types-echantillon`),
  // Sous-types filtrés par type parent (cascade type -> sous-type)
  sousTypesEchantillonRef: (typeId) =>
    request(`/ref/soustypes-echantillon${typeId ? "?type_id=" + typeId : ""}`),

  // Résultats d'analyses (bloc IV)
  resultats: (section, num) =>
    request(`/resultats/${section}/${encodeURIComponent(num)}`),
  enregistrerResultats: (section, num, lignes) =>
    request(`/resultats/${section}/${encodeURIComponent(num)}`, { method: "PUT", body: lignes }),
  // SMA : comparaison des RP aux critères m / M + report de la conformité dans la fiche
  evaluerResultatsSma: (num, lignes) =>
    request(`/resultats/SMA/${encodeURIComponent(num)}/evaluation`, { method: "POST", body: lignes }),
  reporterConformiteSma: (num, conformite) =>
    request(`/resultats/SMA/${encodeURIComponent(num)}/conformite`, { method: "POST", body: { conformite } }),
  creerEchantillon: (body) => request("/echantillons", { method: "POST", body }),
  modifierEchantillon: (num, body) =>
    request(`/echantillons/${encodeURIComponent(num)}`, { method: "PUT", body }),
  supprimerEchantillon: (num) =>
    request(`/echantillons/${encodeURIComponent(num)}`, { method: "DELETE" }),

  // Traitement (section = SMA | SCHA | SSA)
  traitement: (section, num) =>
    request(`/traitement/${section}/${encodeURIComponent(num)}`),
  enregistrerTraitement: (section, body) =>
    request(`/traitement/${section}`, { method: "POST", body }),
  soumettreTraitement: (section, num) =>
    request(`/traitement/${section}/${encodeURIComponent(num)}/soumettre`, { method: "POST" }),
  validerTraitement: (section, num) =>
    request(`/traitement/${section}/${encodeURIComponent(num)}/valider`, { method: "POST" }),
  refuserTraitement: (section, num, motif) =>
    request(`/traitement/${section}/${encodeURIComponent(num)}/refuser`, { method: "POST", body: { motif } }),

  // Admin — comptes
  users: () => request("/admin/users"),
  creerUser: (body) => request("/admin/users", { method: "POST", body }),
  changerRole: (id, role) =>
    request(`/admin/users/${id}/role`, { method: "PATCH", body: { role } }),
  supprimerUser: (id) => request(`/admin/users/${id}`, { method: "DELETE" }),
  reinitialiserMotDePasse: (id, nouveau) =>
    request(`/admin/users/${id}/mot-de-passe`, { method: "POST", body: { nouveau } }),
  deverrouillerUser: (id) => request(`/admin/users/${id}/deverrouiller`, { method: "POST" }),

  // ---- Admin — référentiels (réservé admin) ----
  // Fabricants
  refFabricants: () => request("/admin/ref/fabricants"),
  creerRefFabricant: (body) => request("/admin/ref/fabricants", { method: "POST", body }),
  modifierRefFabricant: (id, body) => request(`/admin/ref/fabricants/${id}`, { method: "PATCH", body }),
  supprimerRefFabricant: (id) => request(`/admin/ref/fabricants/${id}`, { method: "DELETE" }),

  // Catégories
  refCategories: () => request("/admin/ref/categories"),
  creerRefCategorie: (body) => request("/admin/ref/categories", { method: "POST", body }),
  modifierRefCategorie: (id, body) => request(`/admin/ref/categories/${id}`, { method: "PATCH", body }),
  supprimerRefCategorie: (id) => request(`/admin/ref/categories/${id}`, { method: "DELETE" }),

  // Types d'échantillon
  refTypes: () => request("/admin/ref/types"),
  creerRefType: (body) => request("/admin/ref/types", { method: "POST", body }),
  modifierRefType: (id, body) => request(`/admin/ref/types/${id}`, { method: "PATCH", body }),
  supprimerRefType: (id) => request(`/admin/ref/types/${id}`, { method: "DELETE" }),

  // Sous-types (rattachés à un type)
  refSousTypes: (typeId) =>
    request(`/admin/ref/soustypes${typeId ? "?type_id=" + typeId : ""}`),
  creerRefSousType: (body) => request("/admin/ref/soustypes", { method: "POST", body }),
  modifierRefSousType: (id, body) => request(`/admin/ref/soustypes/${id}`, { method: "PATCH", body }),
  supprimerRefSousType: (id) => request(`/admin/ref/soustypes/${id}`, { method: "DELETE" }),

  // Journal d'audit des données (triggers PostgreSQL, lecture seule)
  auditTables: () => request("/admin/audit/tables"),
  journalAudit: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    return request(`/admin/audit${qs ? "?" + qs : ""}`);
  },

  // Tarifs des analyses (facturation)
  refTarifs: (params = "") => request(`/admin/ref/tarifs${params}`),
  creerRefTarif: (body) => request("/admin/ref/tarifs", { method: "POST", body }),
  modifierRefTarif: (id, body) => request(`/admin/ref/tarifs/${id}`, { method: "PATCH", body }),
  supprimerRefTarif: (id) => request(`/admin/ref/tarifs/${id}`, { method: "DELETE" }),
  historiqueRefTarif: (id) => request(`/admin/ref/tarifs/${id}/historique`),
  tarifsSansPrix: () => request("/admin/ref/tarifs/sans-prix"),

  // Facturation (bloc P)
  parametresFacturation: () => request("/facturation/parametres"),
  modifierParametresFacturation: (body) => request("/facturation/parametres", { method: "PUT", body }),
  grilleTarifs: (params = {}) => request(`/facturation/tarifs?${new URLSearchParams(params)}`),
  facturationLignes: (num) => request(`/facturation/echantillons/${encodeURIComponent(num)}`),
  synchroniserFacturation: (num) =>
    request(`/facturation/echantillons/${encodeURIComponent(num)}/synchroniser`, { method: "POST" }),
  ajouterLigneFacturation: (num, body) =>
    request(`/facturation/echantillons/${encodeURIComponent(num)}/lignes`, { method: "POST", body }),
  modifierLigneFacturation: (id, body) => request(`/facturation/lignes/${id}`, { method: "PATCH", body }),
  supprimerLigneFacturation: (id) => request(`/facturation/lignes/${id}`, { method: "DELETE" }),
  // Bulletins et avoirs
  factures: (params = {}) => request(`/facturation/factures?${new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")))}`),
  facture: (id) => request(`/facturation/factures/${id}`),
  facturesEchantillon: (num) => request(`/facturation/echantillons/${encodeURIComponent(num)}/factures`),
  creerFacture: (body) => request("/facturation/factures", { method: "POST", body }),
  modifierFacture: (id, body) => request(`/facturation/factures/${id}`, { method: "PATCH", body }),
  emettreFacture: (id) => request(`/facturation/factures/${id}/emettre`, { method: "POST" }),
  annulerFacture: (id) => request(`/facturation/factures/${id}/annuler`, { method: "POST" }),
  creerAvoir: (id, body) => request(`/facturation/factures/${id}/avoir`, { method: "POST", body }),
  urlPdfFacture: (id) => `${BASE}/facturation/factures/${id}/pdf`,
  // Encaissements, quittances, exonérations
  encaisser: (id, body) => request(`/facturation/factures/${id}/paiements`, { method: "POST", body }),
  annulerPaiement: (id, motif) => request(`/facturation/paiements/${id}/annuler`, { method: "POST", body: { motif } }),
  urlQuittance: (id) => `${BASE}/facturation/paiements/${id}/quittance`,
  exonererFacture: (id, body) => request(`/facturation/factures/${id}/exonerer`, { method: "POST", body }),
  exonererEchantillon: (num, body) =>
    request(`/facturation/echantillons/${encodeURIComponent(num)}/exonerer`, { method: "POST", body }),
  annulerExoneration: (id, motif) => request(`/facturation/exonerations/${id}/annuler`, { method: "POST", body: { motif } }),
  // Page Facturation : impayés, journal de caisse
  impayes: () => request("/facturation/impayes"),
  caisse: (params) => request(`/facturation/caisse?${new URLSearchParams(params)}`),
  urlExportCaisse: (params) => `${BASE}/facturation/caisse/export?${new URLSearchParams(params)}`,

  // Délais de traitement par section (retards du tableau de bord)
  refDelais: () => request("/admin/ref/delais"),
  modifierRefDelai: (section, jours) =>
    request(`/admin/ref/delais/${section}`, { method: "PATCH", body: { jours } }),
};
