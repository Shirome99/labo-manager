import { useState } from "react";
import dayjs from "dayjs";

/**
 * Carte de contrôle (Levey-Jennings) en SVG : une série, moyenne, limites ±2σ / ±3σ.
 * Les points en alerte portent un glyphe « ! » (jamais la couleur seule) ; infobulle au survol
 * avec zone de survol pleine hauteur pour chaque point. La vue tableau est fournie par la page.
 */
const L = 900, H = 300;
const M = { haut: 16, droite: 92, bas: 34, gauche: 56 };
const COULEURS = {
  serie: "#00875A",          // couleur principale de l'application
  ok: "#00875A",
  zone2: "#9A6700",          // avertissement (statut)
  alerte: "#CF222E",         // critique (statut)
  grille: "#E6EDF3",
  limite: "#8B949E",
  moyenne: "#484F58",
  texte: "#6E7681",
};

const fmtN = (v) => (v == null ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 3 }));

export default function CarteControle({ points, stats, unite }) {
  const [survol, setSurvol] = useState(null);
  const pts = (points || []).filter((p) => p.valeur != null);
  if (pts.length === 0 || stats?.moyenne == null) {
    return <div className="carte-vide">Pas encore de mesure à afficher.</div>;
  }

  const { moyenne, sigma } = stats;
  const valeurs = pts.map((p) => p.valeur);
  const bornes = [...valeurs, moyenne, ...(sigma ? [moyenne - 3 * sigma, moyenne + 3 * sigma] : [])];
  let min = Math.min(...bornes), max = Math.max(...bornes);
  const marge = (max - min) * 0.08 || Math.abs(moyenne) * 0.1 || 1;
  min -= marge; max += marge;

  const largeur = L - M.gauche - M.droite, hauteur = H - M.haut - M.bas;
  const pas = pts.length > 1 ? largeur / (pts.length - 1) : 0;
  const x = (i) => M.gauche + (pts.length > 1 ? i * pas : largeur / 2);
  const y = (v) => M.haut + (1 - (v - min) / (max - min)) * hauteur;

  const limites = sigma ? [
    { v: moyenne + 3 * sigma, lib: "+3σ", tirets: "6 3" },
    { v: moyenne + 2 * sigma, lib: "+2σ", tirets: "2 3" },
    { v: moyenne, lib: "Moyenne", tirets: null },
    { v: moyenne - 2 * sigma, lib: "−2σ", tirets: "2 3" },
    { v: moyenne - 3 * sigma, lib: "−3σ", tirets: "6 3" },
  ] : [{ v: moyenne, lib: "Moyenne", tirets: null }];

  // Graduations de l'axe des dates : au plus 6 étiquettes
  const pasDates = Math.max(1, Math.ceil(pts.length / 6));
  const chemin = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.valeur).toFixed(1)}`).join(" ");
  const p = survol != null ? pts[survol] : null;

  return (
    <div className="carte-controle">
      <svg viewBox={`0 0 ${L} ${H}`} role="img"
           aria-label={`Carte de contrôle : ${pts.length} mesures, moyenne ${fmtN(moyenne)}${unite ? " " + unite : ""}`}
           onMouseLeave={() => setSurvol(null)}>
        {/* Limites (recessives) et leurs libellés à droite */}
        {limites.map((l) => (
          <g key={l.lib}>
            <line x1={M.gauche} x2={L - M.droite} y1={y(l.v)} y2={y(l.v)}
                  stroke={l.tirets ? COULEURS.limite : COULEURS.moyenne}
                  strokeWidth={l.tirets ? 1 : 1.5} strokeDasharray={l.tirets || undefined} />
            <text x={L - M.droite + 6} y={y(l.v) + 4} fontSize="11" fill={COULEURS.texte}>
              {l.lib} {fmtN(l.v)}
            </text>
          </g>
        ))}
        {/* Axe des dates */}
        <line x1={M.gauche} x2={L - M.droite} y1={H - M.bas} y2={H - M.bas} stroke={COULEURS.grille} />
        {pts.map((pt, i) => (i % pasDates === 0 || i === pts.length - 1) && (
          <text key={pt.id} x={x(i)} y={H - M.bas + 16} fontSize="11" fill={COULEURS.texte} textAnchor="middle">
            {dayjs(pt.date_mesure).format("DD/MM")}
          </text>
        ))}
        <text x={8} y={M.haut + 4} fontSize="11" fill={COULEURS.texte}>{unite || ""}</text>
        {/* Série */}
        <path d={chemin} fill="none" stroke={COULEURS.serie} strokeWidth="2" strokeLinejoin="round" />
        {survol != null && (
          <line x1={x(survol)} x2={x(survol)} y1={M.haut} y2={H - M.bas} stroke={COULEURS.limite} strokeWidth="1" />
        )}
        {pts.map((pt, i) => {
          const alerte = pt.regles?.length > 0;
          const couleur = alerte ? COULEURS.alerte : pt.zone === "2s" ? COULEURS.zone2 : COULEURS.ok;
          return (
            <g key={pt.id}>
              <circle cx={x(i)} cy={y(pt.valeur)} r={alerte ? 6 : 4.5} fill={couleur}
                      stroke="#FFFFFF" strokeWidth="2" />
              {alerte && (
                <text x={x(i)} y={y(pt.valeur) - 11} fontSize="12" fontWeight="700" fill={COULEURS.alerte}
                      textAnchor="middle">!</text>
              )}
              {/* Zone de survol pleine hauteur */}
              <rect x={x(i) - Math.max(pas, 16) / 2} y={M.haut} width={Math.max(pas, 16)} height={hauteur}
                    fill="transparent" onMouseEnter={() => setSurvol(i)} />
            </g>
          );
        })}
      </svg>
      {p && (
        <div className="carte-infobulle" style={{
          left: `${(x(survol) / L) * 100}%`,
          transform: x(survol) > L * 0.7 ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
        }}>
          <div className="mono">{dayjs(p.date_mesure).format("DD/MM/YYYY")}</div>
          <div><strong>{fmtN(p.valeur)}</strong> {unite || ""}</div>
          <div className="carte-infobulle-zone">
            {p.regles?.length ? p.regles.join(" ; ") : p.zone === "2s" ? "entre 2σ et 3σ (avertissement)" : "dans les limites"}
          </div>
          {p.saisi_par && <div className="carte-infobulle-zone">saisi par {p.saisi_par}</div>}
        </div>
      )}
    </div>
  );
}
