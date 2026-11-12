import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Alert, App, AutoComplete, Button, Card, Col, DatePicker, Flex, Input, InputNumber, Row, Space,
  Table, Tag, Tooltip, Typography,
} from "antd";
import { CloseOutlined, FilePdfOutlined, PlusOutlined, SaveOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";
import BoutonFichier from "../components/BoutonFichier";
import NavigationFile from "../components/NavigationFile";
import { useAvertissementSortie } from "../components/sortie";
import { SelectEchantillon } from "../components/selects";
import { SectionTag, estResponsable } from "../components/ui";

const LIBELLES = {
  SMA: "Microbiologie Alimentaire",
  SCHA: "Sécurité Chimie Hygiène Alimentaire",
  SSA: "Santé Animale",
};

const RP = (n) => Array.from({ length: n }, (_, i) => `rp${i + 1}`);
const CONFIG = {
  SMA:  { rps: RP(5), moyenne: false, conclusion: false, ssa: false },
  SCHA: { rps: RP(9), moyenne: true,  conclusion: true,  ssa: false },
  SSA:  { rps: [],    moyenne: false, conclusion: false, ssa: true },
};

// Classement d'une valeur RP par rapport aux critères m / M (SMA)
const RP_CLASSE = { ok: "rp-ok", marginal: "rp-marginal", depasse: "rp-depasse", illisible: "rp-illisible" };
const RP_TITRE = {
  ok: "≤ m : satisfaisant",
  marginal: "entre m et M : acceptable (compté dans c)",
  depasse: "dépasse le seuil",
  illisible: "valeur non interprétable",
};
const VERDICT_COULEUR = { "Conforme": "green", "Non conforme": "red", "À vérifier": "gold" };
const VERDICT_ALERTE = { "Conforme": "success", "Non conforme": "error", "À vérifier": "warning" };
const VERDICT_DETAIL = {
  "Non conforme": "Au moins un résultat dépasse M (ou plus de c résultats entre m et M).",
  "À vérifier": "Certaines valeurs ne sont pas interprétables.",
  "Conforme": "Tous les résultats évalués respectent les critères.",
};
const FORMAT_DATE_API = "YYYY-MM-DD";

const ligneVide = () => ({
  analyse_effectuee: "", reference_methode: "",
  rp1: "", rp2: "", rp3: "", rp4: "", rp5: "", rp6: "", rp7: "", rp8: "", rp9: "",
  moyenne: "", conclusion: "",
  resultat_analyse: "", criteres_interpretation: "",
  nbre_positifs: "", nbre_negatif: "", nbre_douteux: "",
  responsable_analyse: "", nbre_prelevements: "",
  date_analyse: "", date_sortie: "",
});

const COLONNES_CRITERES = [
  { title: "Critère", dataIndex: "critere", key: "critere" },
  { title: "Microorganisme", dataIndex: "parametre", key: "parametre" },
  ...["n", "c", "m", "M"].map((k) => ({
    title: k, dataIndex: k, key: k, width: 110, render: (v) => <span className="mono">{v}</span>,
  })),
];

export default function Resultats({ user }) {
  const { section } = useParams();
  const cfg = CONFIG[section] || CONFIG.SMA;
  const { message } = App.useApp();

  const [num, setNum] = useState("");
  const [lignes, setLignes] = useState([]);
  const [catalogue, setCatalogue] = useState([]);
  const [criteres, setCriteres] = useState([]);
  const [categorie, setCategorie] = useState(null);
  const [statut, setStatut] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  // Saisie non enregistrée : lignes différentes de celles chargées ou enregistrées
  const [reference, setReference] = useState(null);
  const modifie = Boolean(num) && reference !== null && JSON.stringify(lignes) !== reference;
  const { liberer, confirmerAbandon } = useAvertissementSortie(modifie);

  useEffect(() => {
    api.analysesRef(section)
      .then((d) => setCatalogue(Array.isArray(d) ? d : []))
      .catch(() => setCatalogue([]));
    // Changement de section : on repart d'une page vide
    setNum(""); setLignes([]); setErr(null); setEvaluation(null); setReference(null);
  }, [section]);

  // Ouverture directe : /resultats/SMA?num=… (file de travail, liens)
  const [params] = useSearchParams();
  const numParam = params.get("num");

  const optionsAnalyses = useMemo(
    () => catalogue.map((a) => ({ value: a.nom, label: a.nom })), [catalogue]);

  const [errOuverture, setErrOuverture] = useState(null);
  const ouvrir = async (numero) => {
    setNum(numero); setErr(null); setErrOuverture(null); setStatut(null); setEvaluation(null);
    try {
      const res = await api.resultats(section, numero);
      const arr = Array.isArray(res) ? res : [];
      const chargees = arr.length ? arr.map((r) => ({ ...ligneVide(), ...r })) : [ligneVide()];
      setLignes(chargees);
      setReference(JSON.stringify(chargees));
      const ech = await api.echantillon(numero);
      setStatut(ech.statut || null);
      if (!cfg.ssa) {
        setCategorie(ech.categorie || null);
        if (ech.categorie) {
          api.criteresRef(ech.categorie)
            .then((d) => setCriteres(Array.isArray(d) ? d : []))
            .catch(() => setCriteres([]));
        } else setCriteres([]);
      } else { setCriteres([]); setCategorie(null); }
    } catch (e) { setErrOuverture(e.message); }
  };

  useEffect(() => { if (numParam) ouvrir(numParam); }, [section, numParam]); // eslint-disable-line react-hooks/exhaustive-deps

  const majLigne = (i, valeurs) =>
    setLignes((ls) => ls.map((l, j) => (j === i ? { ...l, ...valeurs } : l)));
  const set = (i, champ) => (e) => majLigne(i, { [champ]: e.target.value });
  // Comptages SSA : stockés en texte comme avant (vide = "")
  const setNombre = (i, champ) => (v) => majLigne(i, { [champ]: v == null ? "" : String(v) });

  const choisirAnalyse = (i) => (nom) => {
    const trouve = catalogue.find((a) => a.nom === nom);
    setLignes((ls) => ls.map((l, j) => (j === i ? {
      ...l,
      analyse_effectuee: nom ?? "",
      reference_methode: trouve?.methode || l.reference_methode || "",
    } : l)));
  };

  // SMA : réévaluation des dépassements à chaque saisie (léger délai)
  useEffect(() => {
    if (section !== "SMA" || !num) return;
    const t = setTimeout(() => {
      api.evaluerResultatsSma(num, lignes).then(setEvaluation).catch(() => setEvaluation(null));
    }, 400);
    return () => clearTimeout(t);
  }, [section, num, lignes]);

  const verrouille = ["À valider", "Validé", "Rapport émis"].includes(statut);
  const reporterConformite = async (valeur) => {
    setErr(null);
    try {
      await api.reporterConformiteSma(num, valeur);
      message.success(`Conformité « ${valeur} » reportée dans la fiche de traitement SMA.`);
    } catch (e) { setErr(e.message); }
  };

  const ajouter = () => setLignes([...lignes, ligneVide()]);
  const retirer = (i) => setLignes(lignes.length > 1 ? lignes.filter((_, j) => j !== i) : [ligneVide()]);

  const enregistrer = async () => {
    setErr(null);
    setEnvoi(true);
    try {
      const propres = lignes.map((l) => ({
        ...l,
        date_analyse: l.date_analyse || null,
        date_sortie: l.date_sortie || null,
      }));
      const r = await api.enregistrerResultats(section, num, propres);
      liberer();
      setReference(JSON.stringify(lignes));
      if (r.evaluation) setEvaluation(r.evaluation);
      message.success(`${r.lignes} analyse(s) enregistrée(s).`);
    } catch (e) { setErr(e.message); }
    finally { setEnvoi(false); }
  };

  // Dates communes à toutes les lignes
  const dateLigne = (champ) => (lignes[0]?.[champ] ? dayjs(String(lignes[0][champ]).slice(0, 10)) : null);
  const setDate = (champ) => (d) =>
    setLignes((ls) => ls.map((l) => ({ ...l, [champ]: d ? d.format(FORMAT_DATE_API) : "" })));

  // Validé : seul un responsable émet le rapport ; Rapport émis : le PDF figé est consultable
  const rapportDispo = statut === "Rapport émis" || (statut === "Validé" && estResponsable(user?.role));

  return (
    <>
      <div className="page-entete">
        <Space size={8} align="center">
          <Typography.Title level={4} className="page-titre">Résultats d'analyses</Typography.Title>
          <SectionTag code={section} />
        </Space>
        <div><Typography.Text type="secondary">{LIBELLES[section]}</Typography.Text></div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Flex gap={12} align="center" wrap>
          <div style={{ flex: "1 1 360px", maxWidth: 560 }}>
            <SelectEchantillon key={section} section={section} value={num || undefined} onChoisir={(n) => confirmerAbandon(() => ouvrir(n))} />
          </div>
          <NavigationFile section={section} num={num} page="resultats" />
        </Flex>
      </div>

      <ErreurChargement message={errOuverture} onReessayer={() => ouvrir(num)} />
      {err && <Alert type="error" title={err} showIcon closable onClose={() => setErr(null)} style={{ marginBottom: 12 }} />}

      {num && (
        <>
          {/* Critères de conformité (bloc III) — SMA/SCHA */}
          {!cfg.ssa && criteres.length > 0 && (
            <Card size="small" title={`Critères de conformité applicables — ${categorie}`} className="bloc">
              <Table size="small" pagination={false} rowKey={(_, i) => i}
                     columns={COLONNES_CRITERES} dataSource={criteres} />
            </Card>
          )}
          {!cfg.ssa && criteres.length === 0 && (
            <Alert type="warning" showIcon className="bloc"
                   title={`Aucun critère trouvé${categorie ? ` pour la catégorie « ${categorie} »` : " : catégorie non renseignée"}. Le bloc III du rapport restera vide.`} />
          )}

          {/* SMA : conclusion proposée à partir des dépassements de seuils */}
          {section === "SMA" && evaluation?.conclusion && (
            <Alert
              className="bloc seuils-bandeau"
              type={VERDICT_ALERTE[evaluation.conclusion] || "info"}
              showIcon
              title={`Conclusion proposée : ${evaluation.conclusion}`}
              description={VERDICT_DETAIL[evaluation.conclusion]}
              action={["Conforme", "Non conforme"].includes(evaluation.conclusion) && !verrouille && (
                <Button size="small" onClick={() => reporterConformite(evaluation.conclusion)}>
                  Reporter « {evaluation.conclusion} » dans la fiche
                </Button>
              )}
            />
          )}

          <Flex justify="space-between" align="baseline">
            <Typography.Text type="secondary" className="sous-titre">Analyses effectuées et résultats</Typography.Text>
            <Typography.Text type="secondary" className="mono" style={{ fontSize: 11 }}>
              {lignes.length} analyse{lignes.length > 1 ? "s" : ""}
            </Typography.Text>
          </Flex>

          {/* Une carte par analyse */}
          {lignes.map((l, i) => {
            const ev = section === "SMA" ? evaluation?.lignes?.[i] : null;
            return (
              <Card
                key={i}
                size="small"
                className={`res-card ${ev?.verdict === "Non conforme" ? "res-card-nc" : ""}`}
                title={
                  <Space size={8}>
                    <span className="res-card-idx">Analyse {i + 1}</span>
                    {ev?.verdict && <Tag color={VERDICT_COULEUR[ev.verdict]}>{ev.verdict}</Tag>}
                  </Space>
                }
                extra={
                  <Tooltip title="Retirer cette analyse">
                    <Button type="text" size="small" icon={<CloseOutlined />} aria-label="Retirer"
                            onClick={() => retirer(i)} />
                  </Tooltip>
                }
              >
                <Row gutter={12}>
                  <Col xs={24} md={14}>
                    <div className="champ-label">Analyse effectuée</div>
                    <AutoComplete
                      value={l.analyse_effectuee || ""}
                      options={optionsAnalyses}
                      onChange={choisirAnalyse(i)}
                      showSearch={{
                        filterOption: (s, o) => String(o?.value).toLowerCase().includes(s.trim().toLowerCase()),
                      }}
                      placeholder="Choisir ou saisir une analyse…"
                      style={{ width: "100%" }}
                    />
                  </Col>
                  <Col xs={24} md={10}>
                    <div className="champ-label">Réf. méthode</div>
                    <Input value={l.reference_methode || ""} onChange={set(i, "reference_methode")}
                           placeholder="Méthode de référence" />
                  </Col>
                </Row>

                {/* SMA / SCHA : prélèvements en grille */}
                {!cfg.ssa && (
                  <>
                    <div className="champ-label" style={{ marginTop: 12 }}>Résultats par prélèvement</div>
                    {section === "SMA" && l.analyse_effectuee && ev && (
                      <Typography.Text type="secondary" className="seuils-critere">
                        {ev.critere
                          ? <>Critère : {ev.critere.parametre} · {ev.critere.m || "—"} · {ev.critere.M || "—"} · {ev.critere.c || ""}</>
                          : "Aucun critère correspondant pour cette analyse dans la catégorie."}
                      </Typography.Text>
                    )}
                    <Row gutter={[8, 8]}>
                      {cfg.rps.map((rp, k) => (
                        <Col key={rp} flex="88px" className={`res-rp ${RP_CLASSE[ev?.rps?.[rp]] || ""}`}>
                          <div className="res-rp-lbl">RP{k + 1}</div>
                          <Tooltip title={RP_TITRE[ev?.rps?.[rp]] || ""}>
                            <Input value={l[rp] || ""} onChange={set(i, rp)} className="res-rp-input" />
                          </Tooltip>
                        </Col>
                      ))}
                      {cfg.moyenne && (
                        <Col flex="110px" className="res-rp res-rp-moy">
                          <div className="res-rp-lbl">Moyenne</div>
                          <Input value={l.moyenne || ""} onChange={set(i, "moyenne")} className="res-rp-input" />
                        </Col>
                      )}
                    </Row>
                    {cfg.conclusion && (
                      <>
                        <div className="champ-label" style={{ marginTop: 12 }}>Conclusion</div>
                        <Input value={l.conclusion || ""} onChange={set(i, "conclusion")}
                               placeholder="Conclusion de l'analyse" />
                      </>
                    )}
                  </>
                )}

                {/* SSA : résultat + interprétation + comptages */}
                {cfg.ssa && (
                  <>
                    <Row gutter={12} style={{ marginTop: 12 }}>
                      <Col xs={24} md={12}>
                        <div className="champ-label">Résultat</div>
                        <Input.TextArea rows={2} value={l.resultat_analyse || ""}
                                        onChange={set(i, "resultat_analyse")}
                                        placeholder="Résultat de l'analyse (ex. Négatif, Absence de lésions…)" />
                      </Col>
                      <Col xs={24} md={12}>
                        <div className="champ-label">Critères d'acceptabilité / interprétation</div>
                        <Input.TextArea rows={2} value={l.criteres_interpretation || ""}
                                        onChange={set(i, "criteres_interpretation")}
                                        placeholder="Interprétation" />
                      </Col>
                    </Row>
                    <Row gutter={12} style={{ marginTop: 12 }}>
                      {[["nbre_positifs", "Positifs"], ["nbre_negatif", "Négatifs"], ["nbre_douteux", "Douteux"]].map(([c, lib]) => (
                        <Col key={c} flex="130px">
                          <div className="champ-label">{lib}</div>
                          <InputNumber min={0} value={l[c] === "" || l[c] == null ? null : Number(l[c])}
                                       onChange={setNombre(i, c)} style={{ width: "100%" }} />
                        </Col>
                      ))}
                    </Row>
                  </>
                )}
              </Card>
            );
          })}

          <Button type="dashed" block icon={<PlusOutlined />} onClick={ajouter} className="bloc">
            Ajouter une analyse
          </Button>

          {/* Dates + actions */}
          <Card size="small">
            <Row gutter={16}>
              <Col xs={24} sm={12} lg={8}>
                <div className="champ-label">Date d'analyse</div>
                <DatePicker format="DD/MM/YYYY" value={dateLigne("date_analyse")}
                            onChange={setDate("date_analyse")} style={{ width: "100%" }} />
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <div className="champ-label">Date de sortie des résultats</div>
                <DatePicker format="DD/MM/YYYY" value={dateLigne("date_sortie")}
                            onChange={setDate("date_sortie")} style={{ width: "100%" }} />
              </Col>
            </Row>
            <Flex justify="space-between" align="center" wrap gap={8} style={{ marginTop: 16 }}>
              <Button type="primary" icon={<SaveOutlined />} loading={envoi} onClick={enregistrer}>
                Enregistrer les résultats
              </Button>
              {rapportDispo ? (
                <BoutonFichier icon={<FilePdfOutlined />} url={api.urlRapport(section, num)}>
                  Voir le rapport PDF
                </BoutonFichier>
              ) : (
                <Typography.Text type="secondary">
                  {statut === "Validé" ? "Rapport à émettre par un responsable" : "Rapport disponible après validation"}
                </Typography.Text>
              )}
            </Flex>
          </Card>
        </>
      )}
    </>
  );
}
