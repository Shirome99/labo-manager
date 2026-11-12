import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Alert, App, Button, Card, Col, Collapse, DatePicker, Drawer, Empty, Flex, Form, Input, Modal, Radio, Row, Segmented, Select,
  Space, Statistic, Table, Tag, Tooltip, Typography,
} from "antd";
import {
  CloseOutlined, CopyOutlined, DeleteOutlined, FileExcelOutlined, FilePdfOutlined, PlayCircleOutlined, PlusOutlined, SaveOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";

const FORMAT_API = "YYYY-MM-DD";
const nf = new Intl.NumberFormat("fr-FR");
const nf1 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formater(v, fmt) {
  if (v === null || v === undefined || v === "") return "—";
  if (fmt === "entier") return nf.format(v);
  if (fmt === "pourcent") return `${nf1.format(v)} %`;
  if (fmt === "montant") return nf2.format(v);
  return nf1.format(v);
}

export const DEFINITION_DEFAUT = {
  jeu: "echantillons", filtres: { periode: "mois_precedent" }, regroupements: ["section"], mesures: ["nb_echantillons"],
};

// Filtres traduisibles en paramètres de la liste des échantillons (lien « Ouvrir dans la liste »)
const URL_LISTE = { section: "section", statut: "statut", decision: "decision", paiement: "paiement" };

function lienListe(definition, resultat, valeurs = {}) {
  if (definition.jeu !== "echantillons" || (definition.filtres?.date_ref || "reception") !== "reception") return null;
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(definition.filtres || {})) {
    if (["du", "au", "periode", "date_ref"].includes(k) || !v?.length) continue;
    if (k === "retard" && v.length === 1 && v[0] === "Oui") { p.set("retard", "1"); continue; }
    if (!URL_LISTE[k] || v.length !== 1) return null;
    p.set(URL_LISTE[k], v[0]);
  }
  for (const [k, v] of Object.entries(valeurs)) {
    if (k === "retard" && v === "Oui") { p.set("retard", "1"); continue; }
    if (k === "section" || !URL_LISTE[k] || (p.has(URL_LISTE[k]) && p.get(URL_LISTE[k]) !== v)) return null;
    p.set(URL_LISTE[k], v);
  }
  if (resultat?.periode?.du) p.set("du", resultat.periode.du);
  if (resultat?.periode?.au) p.set("au", resultat.periode.au);
  return `/echantillons?${p.toString()}`;
}

// Barres horizontales simples (une série : la mesure choisie)
function Barres({ points, mesure }) {
  const max = Math.max(0, ...points.map((p) => p.valeur || 0));
  if (!points.length || !max) return null;
  const affiches = points.slice(0, 30);
  return (
    <div className="req-barres">
      <Typography.Text strong className="req-barres-titre">{mesure.libelle}</Typography.Text>
      {affiches.map((p) => (
        <Tooltip key={p.libelle} title={`${p.libelle} : ${formater(p.valeur, mesure.format)}`} placement="topLeft">
          <div className="req-barre-ligne">
            <span className="req-barre-lib" title={p.libelle}>{p.libelle}</span>
            <span className="req-barre-piste">
              <span className="req-barre" style={{ width: `${((p.valeur || 0) / max) * 100}%` }} />
              <span className="req-barre-val mono">{formater(p.valeur, mesure.format)}</span>
            </span>
          </div>
        </Tooltip>
      ))}
      {points.length > affiches.length && (
        <Typography.Text type="secondary" className="req-note">30 premières valeurs sur {points.length} (voir le tableau).</Typography.Text>
      )}
    </div>
  );
}

// Constructeur : jeu, période, filtres, regroupements, mesures
export function Constructeur({ catalogue, definition, onChange }) {
  const [valeurs, setValeurs] = useState({});      // cache « jeu|dimension » → options
  const jeu = catalogue.jeux.find((j) => j.cle === definition.jeu) || catalogue.jeux[0];
  const dims = catalogue.dimensions.filter((d) => d.jeux.includes(jeu.cle));
  const mesures = catalogue.mesures.filter((m) => m.jeux.includes(jeu.cle));
  const f = definition.filtres || {};
  const actifs = Object.keys(f).filter((k) => !["du", "au", "periode", "date_ref"].includes(k));
  const modePeriode = f.periode ? "relative" : "dates";

  const majFiltres = (nf) => onChange({ ...definition, filtres: nf });
  const chargerValeurs = (dim) => {
    const cle = `${jeu.cle}|${dim}`;
    if (valeurs[cle]) return;
    const d = dims.find((x) => x.cle === dim);
    if (d?.valeurs) { setValeurs((v) => ({ ...v, [cle]: d.valeurs.map((x) => ({ value: x, label: x })) })); return; }
    api.valeursRequete(jeu.cle, dim)
      .then((l) => setValeurs((v) => ({ ...v, [cle]: (Array.isArray(l) ? l : []).map((x) => ({ value: x.valeur, label: `${x.valeur} (${x.n})` })) })))
      .catch(() => setValeurs((v) => ({ ...v, [cle]: [] })));
  };
  useEffect(() => { actifs.forEach(chargerValeurs); }, [jeu.cle, actifs.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  const changerJeu = (cle) => {
    const ok = (k) => catalogue.dimensions.find((d) => d.cle === k)?.jeux.includes(cle);
    const nj = catalogue.jeux.find((j) => j.cle === cle);
    const filtres = Object.fromEntries(Object.entries(f).filter(([k]) => ["du", "au", "periode"].includes(k) || ok(k)));
    if (f.date_ref && nj.dates.some((d) => d.cle === f.date_ref)) filtres.date_ref = f.date_ref;
    const ms = definition.mesures.filter((m) => catalogue.mesures.find((x) => x.cle === m)?.jeux.includes(cle));
    onChange({ ...definition, jeu: cle, filtres, regroupements: definition.regroupements.filter(ok),
               mesures: ms.length ? ms : ["nb_echantillons"], tri: undefined });
  };

  return (
    <Form layout="vertical" className="form-dense">
      <Form.Item label="Jeu de données" tooltip={jeu.description}>
        <Select value={jeu.cle} onChange={changerJeu} options={catalogue.jeux.map((j) => ({ value: j.cle, label: j.libelle }))} />
      </Form.Item>
      <Form.Item label="Période">
        <Space orientation="vertical" style={{ width: "100%" }} size={6}>
          <Segmented block size="small" value={modePeriode}
                     options={[{ value: "relative", label: "Relative" }, { value: "dates", label: "Dates" }]}
                     onChange={(m) => { const { du, au, periode, ...r } = f; majFiltres(m === "relative" ? { ...r, periode: "mois_precedent" } : r); }} />
          {modePeriode === "relative" ? (
            <Select value={f.periode} onChange={(v) => majFiltres({ ...f, periode: v })}
                    options={catalogue.periodes.map((p) => ({ value: p.cle, label: p.libelle }))} />
          ) : (
            <DatePicker.RangePicker format="DD/MM/YYYY" style={{ width: "100%" }} allowEmpty={[true, true]}
                                    value={[f.du ? dayjs(f.du) : null, f.au ? dayjs(f.au) : null]}
                                    onChange={(v) => { const { du, au, ...r } = f; majFiltres({ ...r, ...(v?.[0] ? { du: v[0].format(FORMAT_API) } : {}), ...(v?.[1] ? { au: v[1].format(FORMAT_API) } : {}) }); }} />
          )}
          <Select size="small" value={f.date_ref || jeu.dates[0].cle} onChange={(v) => majFiltres({ ...f, date_ref: v })}
                  options={jeu.dates.map((d) => ({ value: d.cle, label: `Sur la ${d.libelle.toLowerCase()}` }))} />
        </Space>
      </Form.Item>
      <Form.Item label="Filtres">
        <Space orientation="vertical" style={{ width: "100%" }} size={6}>
          {actifs.map((k) => {
            const d = dims.find((x) => x.cle === k);
            return (
              <div key={k} className="req-filtre">
                <Flex justify="space-between" align="center">
                  <Typography.Text type="secondary" className="req-filtre-lib">{d?.libelle || k}</Typography.Text>
                  <Button type="text" size="small" icon={<CloseOutlined />} aria-label="Retirer le filtre"
                          onClick={() => { const { [k]: _, ...r } = f; majFiltres(r); }} />
                </Flex>
                <Select mode="multiple" allowClear style={{ width: "100%" }} placeholder="Toutes les valeurs" maxTagCount="responsive"
                        value={f[k] || []} onChange={(v) => majFiltres({ ...f, [k]: v })}
                        loading={!valeurs[`${jeu.cle}|${k}`]} options={valeurs[`${jeu.cle}|${k}`] || []}
                        showSearch={{ optionFilterProp: "label" }} />
              </div>
            );
          })}
          <Select placeholder={<span><PlusOutlined /> Ajouter un filtre</span>} value={null} style={{ width: "100%" }}
                  showSearch={{ optionFilterProp: "label" }}
                  options={dims.filter((d) => d.filtrable && !actifs.includes(d.cle) && !["mois", "trimestre", "annee"].includes(d.cle))
                    .map((d) => ({ value: d.cle, label: d.libelle }))}
                  onChange={(k) => { majFiltres({ ...f, [k]: [] }); chargerValeurs(k); }} />
        </Space>
      </Form.Item>
      <Form.Item label="Regroupements" tooltip="Deux au plus : le second donne un tableau croisé">
        <Select mode="multiple" maxCount={catalogue.max_regroupements} value={definition.regroupements} placeholder="Aucun (total seul)"
                onChange={(v) => onChange({ ...definition, regroupements: v, tri: undefined })}
                options={dims.map((d) => ({ value: d.cle, label: d.libelle }))} showSearch={{ optionFilterProp: "label" }} />
      </Form.Item>
      <Form.Item label="Mesures">
        <Select mode="multiple" value={definition.mesures}
                onChange={(v) => onChange({ ...definition, mesures: v, tri: undefined })}
                options={mesures.map((m) => ({ value: m.cle, label: m.libelle, title: m.description }))} />
      </Form.Item>
    </Form>
  );
}

// Affichage d'un résultat : statistiques, tableau, tableau croisé, barres
export function Resultat({ resultat, onDetail }) {
  const [vue, setVue] = useState("croise");
  const [mesureCroise, setMesureCroise] = useState(null);
  const regs = resultat.regroupements;
  const mes = resultat.mesures;
  const mc = mes.find((m) => m.cle === mesureCroise) || mes[0];

  if (!regs.length) {
    return (
      <Row gutter={[12, 12]}>
        {mes.map((m) => (
          <Col key={m.cle} xs={12} md={8} lg={6}>
            <Card size="small"><Statistic title={m.libelle} value={formater(resultat.totaux[m.cle], m.format)} /></Card>
          </Col>
        ))}
      </Row>
    );
  }

  const colonnesListe = [
    ...regs.map((g) => ({
      title: g.libelle, dataIndex: g.cle, key: g.cle, onCell: () => ({ style: { minWidth: 140 } }),
      onHeaderCell: () => ({ style: { minWidth: 140 } }),
      sorter: (a, b) => String(a[g.cle]).localeCompare(String(b[g.cle]), "fr", { numeric: true }),
      render: (v) => (v === resultat.non_renseigne || v === "Non renseigné" ? <Typography.Text type="secondary">{v}</Typography.Text> : v),
    })),
    ...mes.map((m) => ({
      title: m.libelle, dataIndex: m.cle, key: m.cle, align: "right", width: 150,
      sorter: (a, b) => (a[m.cle] ?? -Infinity) - (b[m.cle] ?? -Infinity),
      render: (v) => <span className="mono">{formater(v, m.format)}</span>,
    })),
  ];
  const piedListe = () => (
    <Table.Summary fixed>
      <Table.Summary.Row className="req-total">
        {regs.map((g, i) => <Table.Summary.Cell key={g.cle} index={i}>{i === 0 ? "Total" : ""}</Table.Summary.Cell>)}
        {mes.map((m, i) => (
          <Table.Summary.Cell key={m.cle} index={regs.length + i} align="right">
            <span className="mono">{formater(resultat.totaux[m.cle], m.format)}</span>
          </Table.Summary.Cell>
        ))}
      </Table.Summary.Row>
    </Table.Summary>
  );
  const liste = (
    <Table size="small" rowKey={(r) => regs.map((g) => r[g.cle]).join("|")} columns={colonnesListe}
           dataSource={resultat.lignes} summary={piedListe} sticky scroll={{ x: "max-content" }}
           pagination={resultat.lignes.length > 100 ? { pageSize: 100, showSizeChanger: false } : false}
           onRow={(r) => ({ onClick: () => onDetail(Object.fromEntries(regs.map((g) => [g.cle, r[g.cle]]))), className: "req-ligne" })} />
  );

  let croise = null;
  if (regs.length === 2) {
    const [g1, g2] = regs;
    const st1 = resultat.sous_totaux[g1.cle] || [];
    const st2 = resultat.sous_totaux[g2.cle] || [];
    const cell = new Map(resultat.lignes.map((r) => [`${r[g1.cle]}\u0000${r[g2.cle]}`, r]));
    const colonnes = [
      { title: `${g1.libelle} \\ ${g2.libelle}`, dataIndex: "v1", fixed: "left", width: 220 },
      ...st2.map((c) => ({
        title: c[g2.cle], key: c[g2.cle], align: "right", width: 110,
        render: (_, r) => {
          const x = cell.get(`${r.v1}\u0000${c[g2.cle]}`);
          return x ? <a className="mono" onClick={() => onDetail({ [g1.cle]: r.v1, [g2.cle]: c[g2.cle] })}>{formater(x[mc.cle], mc.format)}</a> : "";
        },
      })),
      { title: "Total", key: "_total", align: "right", width: 110, className: "req-col-total",
        render: (_, r) => <a className="mono" onClick={() => onDetail({ [g1.cle]: r.v1 })}>{formater(r.total, mc.format)}</a> },
    ];
    croise = (
      <Table size="small" rowKey="v1" bordered columns={colonnes} scroll={{ x: "max-content" }} sticky
             dataSource={st1.map((r) => ({ v1: r[g1.cle], total: r[mc.cle] }))}
             pagination={st1.length > 100 ? { pageSize: 100, showSizeChanger: false } : false}
             summary={() => (
               <Table.Summary fixed>
                 <Table.Summary.Row className="req-total">
                   <Table.Summary.Cell index={0}>Total</Table.Summary.Cell>
                   {st2.map((c, i) => (
                     <Table.Summary.Cell key={c[g2.cle]} index={i + 1} align="right">
                       <span className="mono">{formater(c[mc.cle], mc.format)}</span>
                     </Table.Summary.Cell>
                   ))}
                   <Table.Summary.Cell index={st2.length + 1} align="right">
                     <span className="mono">{formater(resultat.totaux[mc.cle], mc.format)}</span>
                   </Table.Summary.Cell>
                 </Table.Summary.Row>
               </Table.Summary>
             )} />
    );
  }

  const g = regs[0];
  const source = regs.length === 2 ? resultat.sous_totaux[g.cle] || [] : resultat.lignes;
  const mb = regs.length === 2 ? mc : mes[0];
  return (
    <Space orientation="vertical" style={{ width: "100%" }} size={12}>
      {regs.length === 2 && (
        <Flex gap={8} wrap align="center">
          <Segmented value={vue} onChange={setVue} options={[{ value: "croise", label: "Tableau croisé" }, { value: "liste", label: "Liste" }]} />
          {vue === "croise" && mes.length > 1 && (
            <Select size="middle" style={{ minWidth: 240 }} value={mc.cle} onChange={setMesureCroise}
                    options={mes.map((m) => ({ value: m.cle, label: m.libelle }))} />
          )}
        </Flex>
      )}
      {regs.length === 2 && vue === "croise" ? croise : liste}
      {resultat.tronque && (
        <Alert type="warning" showIcon title={`Résultat limité à ${resultat.lignes.length} lignes sur ${resultat.nb_lignes} ; les totaux portent sur l'ensemble.`} />
      )}
      <Barres mesure={mb} points={source.map((r) => ({ libelle: String(r[g.cle]), valeur: r[mb.cle] }))} />
    </Space>
  );
}

// Lignes détaillées d'une case (tiroir)
export function DetailDrawer({ ouvert, definition, resultat, valeurs, onClose }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [pagination, setPagination] = useState({ page: 1, taille: 50 });
  const [chargement, setChargement] = useState(false);
  // Pagination côté serveur (tâche 30) : une page de lignes à la fois, avec le total
  const charger = (page, taille) => {
    setChargement(true); setErr(null);
    setPagination({ page, taille });
    api.detailRequete(definition, valeurs, page, taille).then(setData).catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => {
    if (!ouvert) return;
    setData(null);
    charger(1, 50);
  }, [ouvert, JSON.stringify(valeurs)]); // eslint-disable-line react-hooks/exhaustive-deps
  const lien = ouvert ? lienListe(definition, resultat, valeurs) : null;
  const titre = Object.values(valeurs || {}).join(" · ") || "Toutes les lignes";
  const colonnes = (data?.colonnes || []).map((c) => ({
    title: c.libelle, dataIndex: c.cle, key: c.cle, ellipsis: true,
    width: c.cle === "num" ? 140 : c.cle === "reception" ? 110 : undefined,
    render: c.cle === "num" ? (v) => (v ? <Link to={`/echantillons/detail/${encodeURIComponent(v)}`} className="mono">{v}</Link> : "—")
      : c.cle === "reception" || c.cle === "date_analyse" ? (v) => (v ? dayjs(v).format("DD/MM/YYYY") : "—")
      : (v) => (v ?? "—"),
  }));
  return (
    <Drawer title={titre} open={ouvert} onClose={onClose} size={1000}
            extra={lien && <Link to={lien}>Ouvrir dans la liste des échantillons</Link>}>
      <ErreurChargement message={err} onReessayer={() => charger(pagination.page, pagination.taille)} />
      <Table size="small" rowKey={(r, i) => `${r.num}-${i}`} loading={chargement} columns={colonnes}
             dataSource={data?.lignes || []}
             pagination={{ current: pagination.page, pageSize: pagination.taille, total: data?.total || 0,
                           showSizeChanger: true, pageSizeOptions: [50, 100, 200],
                           showTotal: (t) => `${t} ligne${t > 1 ? "s" : ""}` }}
             onChange={(p) => charger(p.pageSize !== pagination.taille ? 1 : p.current, p.pageSize)}
             scroll={{ x: "max-content" }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Aucune ligne." /> }} />
    </Drawer>
  );
}

// Modale « Enregistrer sous » : nom, description, visibilité
function ModaleEnregistrer({ ouverte, initiale, definition, onClose, onEnregistre }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  useEffect(() => { if (ouverte) form.setFieldsValue({ visibilite: "personnelle", description: "", ...initiale }); }, [ouverte]); // eslint-disable-line react-hooks/exhaustive-deps
  const relative = !!definition?.filtres?.periode;
  const enregistrer = async (v) => {
    try {
      const r = await api.creerRequeteEnregistree({ ...v, definition });
      message.success("Requête enregistrée.");
      onEnregistre(r);
    } catch (e) { message.error(e.message); }
  };
  return (
    <Modal title="Enregistrer la requête" open={ouverte} okText="Enregistrer" cancelText="Annuler" forceRender
           onOk={() => form.submit()} onCancel={onClose}>
      <Form form={form} layout="vertical" onFinish={enregistrer} className="form-dense">
        <Form.Item label="Nom" name="nom" rules={[{ required: true, whitespace: true, message: "Nom obligatoire" }]}><Input maxLength={150} /></Form.Item>
        <Form.Item label="Description" name="description"><Input.TextArea rows={2} maxLength={2000} /></Form.Item>
        <Form.Item label="Visibilité" name="visibilite">
          <Radio.Group options={[{ value: "personnelle", label: "Personnelle" }, { value: "partagée", label: "Partagée" }]} />
        </Form.Item>
        <Typography.Text type="secondary">
          {relative ? "La période relative est conservée : elle sera recalculée à chaque ouverture."
                    : "Les dates sont enregistrées telles quelles (choisissez une période relative pour un suivi mensuel)."}
        </Typography.Text>
      </Form>
    </Modal>
  );
}

export function titreParDefaut(catalogue, definition) {
  const m = catalogue.mesures.find((x) => x.cle === definition.mesures[0])?.libelle || "Requête";
  const g = definition.regroupements.map((k) => catalogue.dimensions.find((d) => d.cle === k)?.libelle.toLowerCase());
  return g.length ? `${m} par ${g.join(" et ")}` : m;
}

export default function Requetes({ user }) {
  const { message } = App.useApp();
  const [catalogue, setCatalogue] = useState(null);
  const [definition, setDefinition] = useState(DEFINITION_DEFAUT);
  const [resultat, setResultat] = useState(null);
  const [execute, setExecute] = useState(null);       // définition du résultat affiché
  const [chargement, setChargement] = useState(false);
  const [err, setErr] = useState(null);
  const [titre, setTitre] = useState("");
  const [detail, setDetail] = useState(null);         // valeurs de la case cliquée
  const [export_, setExport] = useState(null);
  const [enregistrees, setEnregistrees] = useState([]);
  const [courante, setCourante] = useState(null);     // requête enregistrée ouverte
  const [modale, setModale] = useState(null);         // valeurs initiales de « Enregistrer sous »
  const [params, setParams] = useSearchParams();
  const { modal } = App.useApp();

  const chargerEnregistrees = () => api.requetesEnregistrees()
    .then((d) => setEnregistrees(Array.isArray(d) ? d : [])).catch(() => setEnregistrees([]));
  useEffect(() => { chargerEnregistrees(); }, []);

  const ouvrir = async (id) => {
    try {
      const r = await api.requeteEnregistree(id);
      setCourante(r); setDefinition(r.definition); setTitre(r.nom);
      setParams({ requete: String(r.id) }, { replace: true });
      await executer(r.definition);
    } catch (e) { message.error(e.message); }
  };
  const nouvelle = () => {
    setCourante(null); setTitre(""); setDefinition(DEFINITION_DEFAUT); setParams({}, { replace: true });
    executer(DEFINITION_DEFAUT);
  };
  const enregistrer = async () => {
    if (!courante?.peut_modifier) { setModale({ nom: titre.trim() }); return; }
    try {
      const r = await api.modifierRequeteEnregistree(courante.id, {
        nom: titre.trim() || courante.nom, description: courante.description, visibilite: courante.visibilite, definition });
      setCourante(r); message.success("Requête mise à jour."); chargerEnregistrees();
    } catch (e) { message.error(e.message); }
  };
  const dupliquer = () => setModale({ nom: `Copie de ${courante.nom}`.slice(0, 150), description: courante.description || "" });
  const supprimer = () => modal.confirm({
    title: "Supprimer cette requête enregistrée ?", content: courante.nom, okText: "Supprimer",
    okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try {
        await api.supprimerRequeteEnregistree(courante.id);
        message.success("Requête supprimée."); setCourante(null); setParams({}, { replace: true }); chargerEnregistrees();
      } catch (e) { message.error(e.message); }
    },
  });

  const [essaiCatalogue, setEssaiCatalogue] = useState(0);   // « Réessayer » relance le chargement
  useEffect(() => { setErr(null); api.catalogueRequetes().then(setCatalogue).catch((e) => setErr(e.message)); }, [essaiCatalogue]);

  const executer = async (def = definition) => {
    setChargement(true); setErr(null);
    try {
      const r = await api.executerRequete(def);
      setResultat(r); setExecute(def);
    } catch (e) { setErr(e.message); setResultat(null); }
    finally { setChargement(false); }
  };
  useEffect(() => {
    if (!catalogue) return;
    if (params.get("requete")) ouvrir(params.get("requete"));
    else executer();
  }, [catalogue]); // eslint-disable-line react-hooks/exhaustive-deps

  const titreEffectif = useMemo(() => titre.trim() || (catalogue && execute ? titreParDefaut(catalogue, execute) : ""),
    [titre, catalogue, execute]);
  const exporter = async (format) => {
    setExport(format);
    try { await api.exporterRequete(execute, titreEffectif, format); }
    catch (e) { message.error(e.message); }
    finally { setExport(null); }
  };
  const modifie = execute && JSON.stringify(execute) !== JSON.stringify(definition);

  if (!catalogue) return err ? <ErreurChargement message={err} onReessayer={() => setEssaiCatalogue((n) => n + 1)} /> : <Card loading size="small" />;
  return (
    <>
      <Flex justify="space-between" align="flex-start" className="page-entete">
        <div>
          <Typography.Title level={4} className="page-titre">Requêtes</Typography.Title>
          <Typography.Text type="secondary">
            {courante ? <>Requête enregistrée « {courante.nom} » <Tag>{courante.visibilite === "partagée" ? "Partagée" : "Personnelle"}</Tag>{courante.auteur !== user.username && <>par {courante.auteur}</>}</>
                      : "Compter et extraire les données selon les critères choisis."}
          </Typography.Text>
        </div>
        <Space wrap>
          <Select style={{ width: 300 }} placeholder="Ouvrir une requête enregistrée" value={courante?.id ?? null}
                  showSearch={{ optionFilterProp: "label" }} onChange={ouvrir}
                  options={[
                    { label: "Partagées", title: "Partagées", options: enregistrees.filter((r) => r.visibilite === "partagée").map((r) => ({ value: r.id, label: r.nom, title: r.description })) },
                    { label: "Mes requêtes", title: "Mes requêtes", options: enregistrees.filter((r) => r.visibilite !== "partagée").map((r) => ({ value: r.id, label: r.nom, title: r.description })) },
                  ].filter((g) => g.options.length)} />
          {courante && <Button onClick={nouvelle}>Nouvelle</Button>}
          <Button icon={<SaveOutlined />} onClick={enregistrer}>{courante?.peut_modifier ? "Enregistrer" : "Enregistrer…"}</Button>
          {courante?.peut_modifier && <Button onClick={() => setModale({ nom: "" })}>Enregistrer sous…</Button>}
          {courante && <Button icon={<CopyOutlined />} onClick={dupliquer}>Dupliquer</Button>}
          {courante?.peut_modifier && <Button danger icon={<DeleteOutlined />} onClick={supprimer}>Supprimer</Button>}
        </Space>
      </Flex>
      <Row gutter={16}>
        <Col xs={24} lg={7}>
          <Card size="small" title="Critères" className="req-criteres"
                extra={<Button type="primary" icon={<PlayCircleOutlined />} loading={chargement} onClick={() => executer()}>Exécuter</Button>}>
            <Constructeur catalogue={catalogue} definition={definition} onChange={setDefinition} />
          </Card>
        </Col>
        <Col xs={24} lg={17}>
          <Card size="small" loading={chargement && !resultat}
                title={<Input variant="borderless" className="req-titre" value={titre} onChange={(e) => setTitre(e.target.value)}
                              placeholder={titreEffectif || "Titre"} aria-label="Titre de la requête" />}
                extra={resultat && (
                  <Space>
                    <Button icon={<FileExcelOutlined />} loading={export_ === "xlsx"} onClick={() => exporter("xlsx")}>Excel</Button>
                    <Button icon={<FilePdfOutlined />} loading={export_ === "pdf"} onClick={() => exporter("pdf")}>PDF</Button>
                  </Space>
                )}>
            {err && <Alert type="error" title={err} showIcon style={{ marginBottom: 12 }} />}
            {modifie && <Alert type="info" showIcon style={{ marginBottom: 12 }} title="Critères modifiés : cliquez sur « Exécuter » pour mettre à jour le résultat." />}
            {resultat && (
              <>
                <Flex gap={8} wrap className="req-resume">
                  <Tag>{catalogue.jeux.find((j) => j.cle === resultat.jeu)?.libelle}</Tag>
                  <Tag>{resultat.periode.du || resultat.periode.au
                    ? `${resultat.periode.du ? dayjs(resultat.periode.du).format("DD/MM/YYYY") : "…"} → ${resultat.periode.au ? dayjs(resultat.periode.au).format("DD/MM/YYYY") : "…"}`
                    : "Toutes dates"}</Tag>
                  {resultat.sections.length > 0 && <Tag>Sections : {resultat.sections.join(", ")}</Tag>}
                  {resultat.regroupements.length > 0 && (
                    <Typography.Text type="secondary">Cliquez sur une ligne pour voir les échantillons correspondants.</Typography.Text>
                  )}
                </Flex>
                <Resultat resultat={resultat} onDetail={setDetail} />
                {resultat.sql && (
                  <Collapse size="small" ghost style={{ marginTop: 12 }} items={[{
                    key: "sql", label: "SQL exécuté (contrôle, administrateur)",
                    children: (
                      <>
                        <pre className="req-sql">{resultat.sql}</pre>
                        <pre className="req-sql">{JSON.stringify(resultat.parametres, null, 2)}</pre>
                      </>
                    ),
                  }]} />
                )}
              </>
            )}
          </Card>
        </Col>
      </Row>
      <ModaleEnregistrer ouverte={!!modale} initiale={modale} definition={definition} onClose={() => setModale(null)}
                         onEnregistre={(r) => { setModale(null); setCourante(r); setTitre(r.nom); setParams({ requete: String(r.id) }, { replace: true }); chargerEnregistrees(); }} />
      <DetailDrawer ouvert={!!detail} definition={execute || definition} resultat={resultat} valeurs={detail || {}}
                    onClose={() => setDetail(null)} />
    </>
  );
}
