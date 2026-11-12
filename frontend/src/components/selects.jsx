import { useEffect, useMemo, useState } from "react";
import { AutoComplete, Select, Typography } from "antd";
import { api } from "../api/client";
import { StatutTag } from "./ui";

/**
 * Listes de référentiels (antd), en remplacement des anciens Selecteur*.
 * Même valeur stockée qu'avant : libellé (SelectRef, SelectNature,
 * SelectCategorie) ou id numérique (SelectIdLib).
 */

/** Charge une liste {id, libelle} ; rechargée quand `dep` change. */
function useListe(charger, dep) {
  const [liste, setListe] = useState([]);
  const [chargement, setChargement] = useState(true);
  useEffect(() => {
    let actif = true;
    setChargement(true);
    Promise.resolve(charger())
      .then((l) => { if (actif) setListe(Array.isArray(l) ? l : []); })
      .catch(() => { if (actif) setListe([]); })
      .finally(() => { if (actif) setChargement(false); });
    return () => { actif = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dep]);
  return [liste, chargement];
}

const contient = (saisie, option) =>
  String(option?.value ?? "").toLowerCase().includes(saisie.trim().toLowerCase());

/**
 * Référentiel avec valeur libre autorisée (fabricant, organisme non listé).
 * Stocke le libellé.
 */
export function SelectRef({ value, onChange, charger, placeholder, ...rest }) {
  const [liste, chargement] = useListe(charger, charger);
  const options = useMemo(() => liste.map((x) => ({
    value: x.libelle,
    label: x.ville
      ? <span className="option-ville">{x.libelle}<Typography.Text type="secondary">{x.ville}</Typography.Text></span>
      : x.libelle,
  })), [liste]);
  return (
    <AutoComplete
      value={value || ""}
      onChange={(v) => onChange(v ?? "")}
      options={options}
      showSearch={{ filterOption: contient }}
      placeholder={chargement ? "Chargement…" : (placeholder || "Rechercher…")}
      allowClear
      style={{ width: "100%" }}
      {...rest}
    />
  );
}

/** Référentiel à valeur exacte : stocke le libellé choisi dans la liste. */
function SelectLibelle({ value, onChange, charger, placeholder, ...rest }) {
  const [liste, chargement] = useListe(charger, charger);
  const options = useMemo(() => liste.map((x) => ({ value: x.libelle, label: x.libelle })), [liste]);
  return (
    <Select
      value={value || undefined}
      onChange={(v) => onChange(v ?? "")}
      options={options}
      showSearch={{ optionFilterProp: "label" }}
      loading={chargement}
      placeholder={placeholder || "Choisir…"}
      allowClear
      style={{ width: "100%" }}
      {...rest}
    />
  );
}

export const SelectNature = (p) => <SelectLibelle charger={api.naturesRef} placeholder="Choisir une nature…" {...p} />;
export const SelectCategorie = (p) => <SelectLibelle charger={api.categoriesRef} placeholder="Choisir une catégorie…" {...p} />;

/**
 * Affiche un libellé, stocke un id (type / sous-type d'échantillon).
 * `dep` : recharge la liste quand il change (cascade type → sous-type).
 */
export function SelectIdLib({ value, onChange, charger, placeholder, dep = null, disabled = false, ...rest }) {
  const [liste, chargement] = useListe(charger, dep);
  const options = useMemo(() => liste.map((x) => ({ value: x.id, label: x.libelle })), [liste]);
  // Tant que la liste n'est pas chargée, ne pas afficher l'id brut
  const connu = liste.some((x) => String(x.id) === String(value));
  return (
    <Select
      value={value != null && connu ? options.find((o) => String(o.value) === String(value)).value : undefined}
      onChange={(v) => onChange(v ?? null)}
      options={options}
      showSearch={{ optionFilterProp: "label" }}
      loading={chargement}
      disabled={disabled}
      placeholder={placeholder || "Choisir…"}
      allowClear
      style={{ width: "100%" }}
      {...rest}
    />
  );
}

/**
 * Échantillons déposés dans une section, avec recherche côté serveur (n°, nature,
 * fabricant, client) : les 50 plus récents, puis ceux qui correspondent à la saisie
 * (tâche 30 : la liste complète d'une section peut compter des milliers d'échantillons).
 * `onChoisir(num)` à la sélection.
 */
export function SelectEchantillon({ section, onChoisir, value, ...rest }) {
  const [liste, setListe] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(null);
  const [choix, setChoix] = useState(value);
  const [saisie, setSaisie] = useState("");

  useEffect(() => { setChoix(value); }, [value]);
  useEffect(() => {
    let actif = true;
    setChargement(true);
    setErreur(null);
    const minuteur = setTimeout(() => {
      api.echantillons({ section, q: saisie.trim(), page: 1, taille: 50 })
        .then((d) => { if (actif) setListe(Array.isArray(d?.lignes) ? d.lignes : []); })
        .catch((e) => { if (actif) setErreur(e.message); })
        .finally(() => { if (actif) setChargement(false); });
    }, saisie ? 300 : 0);
    return () => { actif = false; clearTimeout(minuteur); };
  }, [section, saisie]);

  const options = useMemo(() => {
    const opts = liste.map((e) => ({
      value: e.num_echantillon,
      label: (
        <span className="option-echantillon">
          <span className="mono">{e.num_echantillon}</span>
          <Typography.Text type="secondary" ellipsis>{e.nature || "—"}</Typography.Text>
          <StatutTag statut={e.statut} />
        </span>
      ),
    }));
    // L'échantillon ouvert reste affiché même s'il n'est pas dans la page chargée
    if (choix && !opts.some((o) => o.value === choix)) opts.unshift({ value: choix, label: <span className="mono">{choix}</span> });
    return opts;
  }, [liste, choix]);

  return (
    <Select
      value={choix || undefined}
      onChange={(v) => { setChoix(v); if (v) onChoisir(v); }}
      options={options}
      showSearch={{ filterOption: false, onSearch: setSaisie, searchValue: saisie }}
      loading={chargement}
      status={erreur ? "error" : undefined}
      placeholder={chargement ? "Chargement des échantillons…" : "Rechercher un échantillon (n°, nature, client)…"}
      notFoundContent={chargement ? "Recherche…" : erreur || (saisie
        ? "Aucun résultat pour cette recherche."
        : `Aucun échantillon déposé en ${section}.`)}
      optionLabelProp="value"
      style={{ width: "100%", maxWidth: 560 }}
      {...rest}
    />
  );
}
