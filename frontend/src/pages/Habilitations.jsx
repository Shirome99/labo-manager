import { useEffect, useMemo, useState } from "react";
import {
  Alert, App, AutoComplete, Button, Col, DatePicker, Flex, Form, Input, Modal, Row, Segmented, Select, Table, Tag,
  Tooltip, Typography,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement, Vide } from "../components/etats";
import { api } from "../api/client";
import { SectionTag, estResponsable } from "../components/ui";

const FORMAT_API = "YYYY-MM-DD";
const SECTIONS = ["SMA", "SCHA", "SSA"];
const ETAT = {
  "à jour": { couleur: "green", libelle: "À jour" },
  "proche": { couleur: "gold", libelle: "Échéance < 30 j" },
  "échue": { couleur: "red", libelle: "Échue" },
  "à venir": { couleur: "blue", libelle: "À venir" },
};
const fmt = (d) => (d ? dayjs(d).format("DD/MM/YYYY") : "—");

function EtatTag({ etat }) {
  const e = ETAT[etat] || ETAT["à jour"];
  return <Tag color={e.couleur} style={{ marginInlineEnd: 0 }}>{e.libelle}</Tag>;
}

export default function Habilitations({ user }) {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const responsable = estResponsable(user.role);
  const [rows, setRows] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState(null);
  const [comptes, setComptes] = useState([]);
  const [catalogue, setCatalogue] = useState([]);
  const [vue, setVue] = useState("Liste");
  const [section, setSection] = useState("SMA");
  const [edition, setEdition] = useState(null);   // null : fermé ; {} : nouvelle ; objet : modification
  const sectionForm = Form.useWatch("section", form);

  const charger = () => {
    setChargement(true);
    return api.habilitations()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => {
    charger();
    if (responsable) api.utilisateursHabilitables().then((d) => setComptes(Array.isArray(d) ? d : [])).catch(() => setComptes([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!sectionForm) return;
    api.analysesRef(sectionForm).then((d) => setCatalogue(Array.isArray(d) ? d : [])).catch(() => setCatalogue([]));
  }, [sectionForm]);

  // Analyses proposées : catalogue de la section + analyses déjà présentes dans la matrice
  const optionsAnalyses = useMemo(() => {
    const noms = new Set(catalogue.map((a) => a.nom));
    rows.filter((h) => h.section === sectionForm).forEach((h) => noms.add(h.nom_analyse));
    return [...noms].sort((a, b) => a.localeCompare(b, "fr")).map((n) => ({ value: n }));
  }, [catalogue, rows, sectionForm]);

  const ouvrir = (h) => {
    setEdition(h || {});
    form.setFieldsValue(h
      ? { ...h, date_qualification: dayjs(h.date_qualification), date_echeance: h.date_echeance ? dayjs(h.date_echeance) : null }
      : { section: vue === "Matrice" ? section : undefined, date_qualification: dayjs() });
  };
  const enregistrer = async (v) => {
    const body = { ...v, date_qualification: v.date_qualification.format(FORMAT_API),
                   date_echeance: v.date_echeance ? v.date_echeance.format(FORMAT_API) : null };
    try {
      if (edition?.id) await api.modifierHabilitation(edition.id, body);
      else await api.creerHabilitation(body);
      message.success(edition?.id ? "Habilitation modifiée." : "Habilitation ajoutée.");
      setEdition(null);
      form.resetFields();
      charger();
    } catch (e) { message.error(e.message); }
  };
  const supprimer = (h) => modal.confirm({
    title: "Retirer cette habilitation ?",
    content: `${h.utilisateur} — ${h.nom_analyse} (${h.section})`,
    okText: "Retirer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { await api.supprimerHabilitation(h.id); message.success("Habilitation retirée."); charger(); }
      catch (e) { message.error(e.message); }
    },
  });

  const colonnes = [
    { title: "Utilisateur", dataIndex: "utilisateur", width: 140, sorter: (a, b) => a.utilisateur.localeCompare(b.utilisateur, "fr"),
      filters: [...new Set(rows.map((r) => r.utilisateur))].map((u) => ({ text: u, value: u })),
      onFilter: (v, r) => r.utilisateur === v },
    { title: "Section", dataIndex: "section", width: 90, render: (s) => <SectionTag code={s} />,
      filters: SECTIONS.map((s) => ({ text: s, value: s })), onFilter: (v, r) => r.section === v },
    { title: "Analyse", dataIndex: "nom_analyse", ellipsis: true, sorter: (a, b) => a.nom_analyse.localeCompare(b.nom_analyse, "fr") },
    { title: "Qualification", dataIndex: "date_qualification", width: 110, render: (v) => <span className="mono">{fmt(v)}</span> },
    { title: "Échéance", dataIndex: "date_echeance", width: 110, render: (v) => <span className="mono">{v ? fmt(v) : "Sans"}</span>,
      sorter: (a, b) => (a.date_echeance || "9999").localeCompare(b.date_echeance || "9999") },
    { title: "État", dataIndex: "etat", width: 140, render: (v) => <EtatTag etat={v} />,
      filters: Object.entries(ETAT).map(([value, e]) => ({ text: e.libelle, value })), onFilter: (v, r) => r.etat === v },
    { title: "Habilité par", dataIndex: "habilite_par", width: 120 },
    ...(responsable ? [{
      title: "", key: "actions", width: 140, align: "right",
      render: (_, r) => (
        <Flex gap={4} justify="flex-end">
          <Button type="link" size="small" className="btn-lien" onClick={() => ouvrir(r)}>Modifier</Button>
          <Button type="link" size="small" danger className="btn-lien" onClick={() => supprimer(r)}>Retirer</Button>
        </Flex>
      ),
    }] : []),
  ];

  // Matrice utilisateur × analyse pour une section
  const matrice = useMemo(() => {
    const hs = rows.filter((h) => h.section === section);
    const analyses = [...new Set(hs.map((h) => h.nom_analyse))].sort((a, b) => a.localeCompare(b, "fr"));
    const parUser = new Map();
    hs.forEach((h) => {
      if (!parUser.has(h.user_id)) parUser.set(h.user_id, { user_id: h.user_id, utilisateur: h.utilisateur, cellules: {} });
      parUser.get(h.user_id).cellules[h.nom_analyse] = h;
    });
    const lignes = [...parUser.values()].sort((a, b) => a.utilisateur.localeCompare(b.utilisateur, "fr"));
    const cols = [
      { title: "Utilisateur", dataIndex: "utilisateur", fixed: "left", width: 140 },
      ...analyses.map((a) => ({
        title: <Tooltip title={a}><span>{a}</span></Tooltip>, key: a, width: 130, align: "center", ellipsis: true,
        render: (_, l) => {
          const h = l.cellules[a];
          if (!h) return <Typography.Text type="secondary">—</Typography.Text>;
          const tag = <Tooltip title={`Qualifié le ${fmt(h.date_qualification)} · échéance ${h.date_echeance ? fmt(h.date_echeance) : "aucune"}`}><span><EtatTag etat={h.etat} /></span></Tooltip>;
          return responsable ? <a onClick={() => ouvrir(h)}>{tag}</a> : tag;
        },
      })),
    ];
    return { lignes, cols, vide: analyses.length === 0 };
  }, [rows, section, responsable]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <Flex justify="space-between" align="flex-start" className="page-entete">
        <div>
          <Typography.Title level={4} className="page-titre">Habilitations</Typography.Title>
          <Typography.Text type="secondary">
            {responsable ? "Matrice utilisateur × analyse. Un résultat ne peut être enregistré que par un analyste habilité et à jour."
                         : "Vos habilitations par analyse."}
          </Typography.Text>
        </div>
        {responsable && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouvelle habilitation</Button>}
      </Flex>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />

      <Flex gap={12} style={{ marginBottom: 12 }}>
        <Segmented options={["Liste", "Matrice"]} value={vue} onChange={setVue} />
        {vue === "Matrice" && <Segmented options={SECTIONS} value={section} onChange={setSection} />}
      </Flex>

      {vue === "Liste" ? (
        <Table size="small" rowKey="id" columns={colonnes} dataSource={rows} loading={chargement}
               pagination={rows.length > 50 ? { pageSize: 50 } : false}
               locale={{ emptyText: <Vide texte="Aucune habilitation."
                 action={responsable && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouvelle habilitation</Button>} /> }} />
      ) : (
        <Table size="small" rowKey="user_id" columns={matrice.cols} dataSource={matrice.lignes} loading={chargement}
               pagination={false} scroll={{ x: "max-content" }} bordered
               locale={{ emptyText: `Aucune habilitation en ${section}.` }} />
      )}

      <Modal title={edition?.id ? "Modifier l'habilitation" : "Nouvelle habilitation"} open={edition !== null}
             okText="Enregistrer" cancelText="Annuler" onOk={() => form.submit()} width={640}
             onCancel={() => { setEdition(null); form.resetFields(); }} forceRender>
        <Form form={form} layout="vertical" onFinish={enregistrer} className="form-dense">
          <Row gutter={16}>
            <Col xs={24} sm={12}><Form.Item label="Utilisateur" name="user_id" rules={[{ required: true, message: "Choisissez l'utilisateur" }]}>
              <Select showSearch={{ optionFilterProp: "label" }} placeholder="Utilisateur"
                      options={comptes.map((c) => ({ value: c.id, label: `${c.nom} (${c.role})` }))} />
            </Form.Item></Col>
            <Col xs={24} sm={12}><Form.Item label="Section" name="section" rules={[{ required: true, message: "Choisissez la section" }]}>
              <Select options={SECTIONS.map((s) => ({ value: s, label: s }))} placeholder="Section" />
            </Form.Item></Col>
            <Col xs={24}><Form.Item label="Analyse" name="nom_analyse" rules={[{ required: true, whitespace: true, message: "Analyse obligatoire" }]}
                                    tooltip="Même libellé que dans les résultats (comparé sans tenir compte des majuscules)">
              <AutoComplete options={optionsAnalyses} disabled={!sectionForm} placeholder={sectionForm ? "Nom de l'analyse" : "Choisissez d'abord la section"}
                            filterOption={(s, o) => o.value.toLowerCase().includes(s.toLowerCase())} />
            </Form.Item></Col>
            <Col xs={12}><Form.Item label="Date de qualification" name="date_qualification" rules={[{ required: true, message: "Date obligatoire" }]}>
              <DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} />
            </Form.Item></Col>
            <Col xs={12}><Form.Item label="Échéance" name="date_echeance" tooltip="Vide = sans échéance"
                                    dependencies={["date_qualification"]}
                                    rules={[({ getFieldValue }) => ({ validator: (_, v) => (!v || !getFieldValue("date_qualification") || !v.isBefore(getFieldValue("date_qualification"), "day")
                                      ? Promise.resolve() : Promise.reject(new Error("L'échéance doit suivre la qualification"))) })]}>
              <DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} />
            </Form.Item></Col>
            <Col xs={24}><Form.Item label="Observations" name="observations"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </>
  );
}
