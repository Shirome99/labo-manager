import { Tag } from "antd";

/**
 * Éléments d'affichage partagés (antd) : statuts, sections, rôles.
 * Une couleur fixe par statut et par section, reprise sur toutes les pages.
 */
export const STATUTS = ["Reçu", "En cours", "À valider", "Validé", "Rapport émis"];

export const STATUT_COULEUR = {
  "Reçu": "default",
  "En cours": "blue",
  "À valider": "gold",
  "Validé": "green",
  "Rapport émis": "#00875A",
};

export const SECTIONS = [
  { code: "SMA", nom: "Microbiologie", key: "totalSMA" },
  { code: "SCHA", nom: "Chimie", key: "totalSCHA" },
  { code: "SSA", nom: "Santé Animale", key: "totalSSA" },
];

export const ROLE_COULEUR = {
  admin: "#00875A", responsable: "#0E7490", user: "#484F58", sma: "#0550AE", scha: "#6E40C9", ssa: "#953800",
};

// Mêmes règles que le serveur (app/core/security.py)
export const ROLES = ["admin", "responsable", "sma", "scha", "ssa", "user"];
export const ROLES_RESPONSABLES = ["admin", "responsable"];   // valider, renvoyer, émettre, erratum
export const ROLES_GLOBAUX = ["admin", "responsable", "user"]; // voient toutes les sections
export const ROLE_SECTION = { sma: "SMA", scha: "SCHA", ssa: "SSA" };     // rôle de section → sa section
export const ROLES_FACTURATION = ["admin", "user"];  // bulletins, encaissements (accueil et admin)
export const estResponsable = (role) => ROLES_RESPONSABLES.includes(role);

// Règle de mot de passe (identique au serveur : security.mot_de_passe_conforme)
export const REGLES_MOT_DE_PASSE = [
  { required: true, message: "Saisissez un mot de passe" },
  {
    validator: (_, v) => (!v || (v.length >= 10 && /[A-Za-zÀ-ÿ]/.test(v) && /\d/.test(v))
      ? Promise.resolve()
      : Promise.reject(new Error("Au moins 10 caractères, dont des lettres et des chiffres"))),
  },
];

export function StatutTag({ statut }) {
  if (!statut) return null;
  return <Tag color={STATUT_COULEUR[statut] || "default"} style={{ marginInlineEnd: 0 }}>{statut}</Tag>;
}

// Décision de réception (migration 017) ; NULL = non renseigné (antérieur) = accepté
export const DECISIONS = ["Accepté", "Accepté sous réserve", "Refusé"];
export const NON_CONFORMITES = [
  ["nc_temperature", "Température"], ["nc_contenant", "Contenant"],
  ["nc_quantite", "Quantité insuffisante"], ["nc_etiquetage", "Étiquetage"],
  ["nc_delai", "Délai d'acheminement"], ["nc_autre", "Autre"],
];

/** Tag de décision de réception : rien pour « Accepté », sinon « Refusé » / « Sous réserve ». */
export function DecisionTag({ decision }) {
  if (decision === "Refusé") return <Tag color="red" style={{ marginInlineEnd: 0 }}>Refusé</Tag>;
  if (decision === "Accepté sous réserve") return <Tag color="gold" style={{ marginInlineEnd: 0 }}>Sous réserve</Tag>;
  return null;
}

// Statut de paiement (champ « Payement », calculé par la facturation) ; vide = « Non concerné » ; « À payer » = ancienne valeur
export const STATUTS_PAIEMENT = ["Non concerné", "Non payé", "Partiellement payé", "Payé", "Exonéré", "Avoir total"];
const COULEUR_PAIEMENT = {
  "Non payé": "red", "À payer": "red", "Partiellement payé": "gold", "Payé": "green", "Exonéré": "blue", "Avoir total": "purple",
};
export function PaiementTag({ statut }) {
  if (!statut || statut === "Non concerné") return null;
  return <Tag color={COULEUR_PAIEMENT[statut] || "default"} style={{ marginInlineEnd: 0 }}>{statut}</Tag>;
}

/** Montant en dirhams : 1250.5 -> « 1 250,50 DH » (vide -> « — »). */
export function formatDH(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " DH";
}

/** Pastille de section (SMA / SCHA / SSA) ou de rôle, même code couleur. */
export function SectionTag({ code }) {
  if (!code) return null;
  const c = String(code);
  return (
    <Tag color={ROLE_COULEUR[c.toLowerCase()] || "default"} className="tag-code" style={{ marginInlineEnd: 0 }}>
      {c.toUpperCase()}
    </Tag>
  );
}
