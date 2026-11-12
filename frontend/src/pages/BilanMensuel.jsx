import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert, App, Button, Card, Col, DatePicker, Flex, Input, Row, Select, Space, Switch, Table, Tag, Typography,
} from "antd";
import {
  ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, EyeOutlined, FileExcelOutlined, FilePdfOutlined, PlusOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement, Vide } from "../components/etats";
import { api } from "../api/client";
import BoutonFichier from "../components/BoutonFichier";
import { ROLE_SECTION } from "../components/ui";
import { formater, Resultat } from "./Requetes";

const SECTIONS = ["SMA", "SCHA", "SSA"];

// Composition du bilan (admin) : ordre, titre, requête partagée, actif
function Modele({ admin }) {
  const { message } = App.useApp();
  const [blocs, setBlocs] = useState(null);
  const [requetes, setRequetes] = useState([]);
  const [modifie, setModifie] = useState(false);
  const [errModele, setErrModele] = useState(null);
  const charger = () => { setErrModele(null); return api.modeleBilan().then((d) => { setBlocs(Array.isArray(d) ? d : []); setModifie(false); }).catch((e) => { setBlocs([]); setErrModele(e.message); }); };
  useEffect(() => {
    charger();
    api.requetesEnregistrees().then((d) => setRequetes((Array.isArray(d) ? d : []).filter((r) => r.visibilite === "partagée"))).catch(() => {});
  }, []);
  const maj = (i, champs) => { setBlocs((b) => b.map((x, j) => (j === i ? { ...x, ...champs } : x))); setModifie(true); };
  const deplacer = (i, d) => {
    setBlocs((b) => { const n = [...b]; [n[i], n[i + d]] = [n[i + d], n[i]]; return n; });
    setModifie(true);
  };
  const enregistrer = async () => {
    try {
      const d = await api.enregistrerModeleBilan(blocs.map(({ id, type_bloc, titre, requete_id, actif }) => ({ id, type_bloc, titre, requete_id, actif })));
      setBlocs(d); setModifie(false); message.success("Modèle du bilan enregistré.");
    } catch (e) { message.error(e.message); }
  };
  const colonnes = [
    { title: "N°", key: "n", width: 50, render: (_, __, i) => <span className="mono">{i + 1}</span> },
    { title: "Titre", dataIndex: "titre", render: (v, _, i) => (admin ? <Input value={v} maxLength={150} onChange={(e) => maj(i, { titre: e.target.value })} /> : v) },
    { title: "Contenu", key: "contenu", width: 340, render: (_, b, i) => (b.type_bloc === "synthese"
      ? <Tag>Synthèse (calculée)</Tag>
      : admin
        ? <Select style={{ width: "100%" }} value={b.requete_id} showSearch={{ optionFilterProp: "label" }}
                  onChange={(v) => maj(i, { requete_id: v })} options={requetes.map((r) => ({ value: r.id, label: r.nom }))} />
        : <Link to={`/requetes?requete=${b.requete_id}`}>{b.requete_nom}</Link>) },
    { title: "Actif", dataIndex: "actif", width: 70, render: (v, _, i) => <Switch size="small" checked={v} disabled={!admin} onChange={(x) => maj(i, { actif: x })} /> },
    ...(admin ? [{
      title: "", key: "actions", width: 120, align: "right",
      render: (_, __, i) => (
        <Space size={0}>
          <Button type="text" size="small" icon={<ArrowUpOutlined />} disabled={i === 0} onClick={() => deplacer(i, -1)} aria-label="Monter" />
          <Button type="text" size="small" icon={<ArrowDownOutlined />} disabled={i === blocs.length - 1} onClick={() => deplacer(i, 1)} aria-label="Descendre" />
          <Button type="text" size="small" danger icon={<DeleteOutlined />} aria-label="Retirer"
                  onClick={() => { setBlocs((b) => b.filter((_, j) => j !== i)); setModifie(true); }} />
        </Space>
      ),
    }] : []),
  ];
  return (
    <Card size="small" title="Composition du bilan"
          extra={admin && (
            <Space>
              <Button icon={<PlusOutlined />} onClick={() => { setBlocs((b) => [...b, { type_bloc: "requete", titre: "Nouveau bloc", requete_id: requetes[0]?.id ?? null, actif: true }]); setModifie(true); }}>Ajouter un bloc</Button>
              {!blocs?.some((b) => b.type_bloc === "synthese") && (
                <Button onClick={() => { setBlocs((b) => [{ type_bloc: "synthese", titre: "Synthèse du mois", requete_id: null, actif: true }, ...b]); setModifie(true); }}>Ajouter la synthèse</Button>
              )}
              <Button disabled={!modifie} onClick={charger}>Annuler</Button>
              <Button type="primary" disabled={!modifie} onClick={enregistrer}>Enregistrer</Button>
            </Space>
          )}>
      <Typography.Paragraph type="secondary" className="req-note">
        Chaque bloc est une requête enregistrée partagée, exécutée sur le mois et la section du bilan (sa période est remplacée par le mois choisi ; une requête sans période décrit la situation à la date de génération).
      </Typography.Paragraph>
      <ErreurChargement message={errModele} onReessayer={charger} />
      <Table size="small" rowKey={(b, i) => b.id ?? `n${i}`} columns={colonnes} dataSource={blocs || []} loading={blocs === null} pagination={false} />
    </Card>
  );
}

export default function BilanMensuel({ user }) {
  const { message } = App.useApp();
  const sectionRole = ROLE_SECTION[user.role] || null;
  const [mois, setMois] = useState(dayjs().subtract(1, "month").startOf("month"));
  const [section, setSection] = useState(sectionRole);
  const [enCours, setEnCours] = useState(null);
  const [apercu, setApercu] = useState(null);
  const [chargeApercu, setChargeApercu] = useState(false);
  const [historique, setHistorique] = useState([]);
  const [err, setErr] = useState(null);
  const m = mois.format("YYYY-MM");

  const [errHisto, setErrHisto] = useState(null);
  const chargerHistorique = () => { setErrHisto(null); return api.historiqueBilans().then((d) => setHistorique(Array.isArray(d) ? d : [])).catch((e) => { setHistorique([]); setErrHisto(e.message); }); };
  useEffect(() => { chargerHistorique(); }, []);
  useEffect(() => { setApercu(null); }, [m, section]);

  const generer = async (format) => {
    setEnCours(format); setErr(null);
    try {
      await api.genererBilan(m, section, format);
      message.success("Bilan généré et archivé.");
      chargerHistorique();
    } catch (e) { setErr(e.message); }
    finally { setEnCours(null); }
  };
  const voir = async () => {
    setChargeApercu(true); setErr(null);
    try { setApercu(await api.apercuBilan(m, section)); } catch (e) { setErr(e.message); }
    finally { setChargeApercu(false); }
  };

  const colonnesHisto = [
    { title: "Mois", dataIndex: "mois", width: 110, render: (v) => dayjs(`${v}-01`).format("MMMM YYYY") },
    { title: "Section", dataIndex: "section", width: 90, render: (v) => v || "Toutes" },
    { title: "Format", dataIndex: "format", width: 80, render: (v) => <Tag>{v.toUpperCase()}</Tag> },
    { title: "Version", dataIndex: "version", width: 80, align: "right" },
    { title: "Généré le", dataIndex: "genere_le", width: 150, render: (v) => dayjs(v).format("DD/MM/YYYY HH:mm") },
    { title: "Par", dataIndex: "auteur", width: 170, render: (v, r) => <>{v}{r.source === "script" && <Tag style={{ marginInlineStart: 6 }}>Tâche planifiée</Tag>}</> },
    { title: "SHA-256", dataIndex: "sha256", ellipsis: true, render: (v) => <Typography.Text className="mono" copyable={{ text: v }}>{v.slice(0, 16)}…</Typography.Text> },
    { title: "", key: "dl", width: 110, align: "right",
      render: (_, r) => <BoutonFichier type="link" size="small" className="btn-lien" url={api.urlBilan(r.id)} telecharger
                                       nom={`bilan_${r.id}`}>Télécharger</BoutonFichier> },
  ];

  return (
    <>
      <Flex justify="space-between" align="flex-start" className="page-entete">
        <div>
          <Typography.Title level={4} className="page-titre">Bilan mensuel</Typography.Title>
          <Typography.Text type="secondary">Bilan d'activité remis à la direction et à l'ONSSA. Chaque génération est archivée.</Typography.Text>
        </div>
      </Flex>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Flex gap={12} wrap align="center">
          <span>Mois</span>
          <DatePicker picker="month" format="MMMM YYYY" value={mois} allowClear={false} onChange={(v) => v && setMois(v.startOf("month"))}
                      disabledDate={(d) => d && d.isAfter(dayjs(), "month")} />
          <span>Section</span>
          <Select style={{ width: 170 }} value={section} disabled={!!sectionRole} onChange={setSection}
                  options={[{ value: null, label: "Toutes les sections" }, ...SECTIONS.map((s) => ({ value: s, label: s }))]} />
          <Button icon={<EyeOutlined />} loading={chargeApercu} onClick={voir}>Aperçu</Button>
          <Button type="primary" icon={<FilePdfOutlined />} loading={enCours === "pdf"} onClick={() => generer("pdf")}>Générer PDF</Button>
          <Button icon={<FileExcelOutlined />} loading={enCours === "xlsx"} onClick={() => generer("xlsx")}>Générer Excel</Button>
        </Flex>
        {err && <Alert type="error" title={err} showIcon style={{ marginTop: 12 }} />}
      </Card>

      {apercu && (
        <Card size="small" title={apercu.titre} style={{ marginBottom: 16 }}>
          {apercu.blocs.map((b, i) => (
            <div key={i} className="bilan-bloc">
              <Typography.Title level={5}>{i + 1}. {b.titre}</Typography.Title>
              {b.type === "synthese" && (
                <Table size="small" rowKey="cle" pagination={false} dataSource={apercu.synthese} columns={[
                  { title: "Indicateur", dataIndex: "libelle" },
                  { title: apercu.libelle_mois, dataIndex: "valeur", align: "right", width: 140, render: (v, s) => <strong className="mono">{formater(v, s.format)}</strong> },
                  { title: apercu.precedent, dataIndex: "precedent", align: "right", width: 140, render: (v, s) => <span className="mono">{formater(v, s.format)}</span> },
                  { title: "Évolution", dataIndex: "evolution", align: "right", width: 110, render: (v) => <span className="mono">{v}</span> },
                ]} />
              )}
              {b.type === "erreur" && <Alert type="warning" showIcon title={b.note} />}
              {b.type === "requete" && <Resultat resultat={b.resultat} onDetail={() => {}} />}
              {b.type === "requete" && b.note && <Typography.Text type="secondary" className="req-note">{b.note}</Typography.Text>}
            </div>
          ))}
        </Card>
      )}

      <Row gutter={16}>
        <Col xs={24}>
          <Card size="small" title="Bilans archivés" style={{ marginBottom: 16 }}>
            <ErreurChargement message={errHisto} onReessayer={chargerHistorique} />
            <Table size="small" rowKey="id" columns={colonnesHisto} dataSource={historique} scroll={{ x: "max-content" }}
                   pagination={historique.length > 20 ? { pageSize: 20, showSizeChanger: false } : false}
                   locale={{ emptyText: <Vide texte="Aucun bilan généré : choisissez un mois puis « Générer PDF » ou « Générer Excel »." /> }} />
          </Card>
        </Col>
        <Col xs={24}>
          <Modele admin={user.role === "admin"} />
        </Col>
      </Row>
    </>
  );
}
