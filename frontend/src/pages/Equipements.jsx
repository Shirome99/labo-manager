import { useEffect, useState } from "react";
import {
  Alert, App, Button, Card, Col, DatePicker, Flex, Form, Input, InputNumber, Modal, Row, Select, Space, Switch,
  Table, Tag, Typography,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement, Vide } from "../components/etats";
import { api } from "../api/client";
import { SectionTag, estResponsable } from "../components/ui";

const FORMAT_API = "YYYY-MM-DD";
export const ECHEANCE = {
  "à jour": { couleur: "green", libelle: "À jour" },
  "proche": { couleur: "gold", libelle: "Échéance < 30 j" },
  "échu": { couleur: "red", libelle: "Échu" },
  "non soumis": { couleur: "default", libelle: "Non soumis" },
  "inactif": { couleur: "default", libelle: "Inactif" },
};
const TYPES = ["Étalonnage", "Vérification", "Maintenance", "Panne", "Réparation"];
const fmt = (d) => (d ? dayjs(d).format("DD/MM/YYYY") : "—");
const DATES = ["date_dernier_etalonnage", "date_derniere_verification"];

export function EcheanceTag({ statut }) {
  const e = ECHEANCE[statut] || ECHEANCE["non soumis"];
  return <Tag color={e.couleur} style={{ marginInlineEnd: 0 }}>{e.libelle}</Tag>;
}

// Historique d'un équipement + saisie d'un événement
function Historique({ eq, peutSaisir, onChange }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [lignes, setLignes] = useState(null);
  const charger = () => api.evenementsEquipement(eq.id).then((d) => setLignes(Array.isArray(d) ? d : [])).catch(() => setLignes([]));
  useEffect(() => { charger(); }, [eq.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const ajouter = async (v) => {
    try {
      await api.ajouterEvenementEquipement(eq.id, { ...v, date_evenement: v.date_evenement.format(FORMAT_API) });
      message.success("Événement enregistré.");
      form.resetFields();
      charger();
      onChange();
    } catch (e) { message.error(e.message); }
  };
  const type = Form.useWatch("type_evenement", form);

  return (
    <div className="equipement-historique">
      <Table size="small" rowKey="id" pagination={false} loading={lignes === null} dataSource={lignes || []}
             locale={{ emptyText: "Aucun événement." }}
             columns={[
               { title: "Date", dataIndex: "date_evenement", width: 110, render: fmt },
               { title: "Type", dataIndex: "type_evenement", width: 120 },
               { title: "Résultat", dataIndex: "resultat", width: 120,
                 render: (v) => (v ? <Tag color={v === "Conforme" ? "green" : "red"}>{v}</Tag> : "—") },
               { title: "Description", dataIndex: "description", render: (v) => v || "—" },
               { title: "Saisi par", dataIndex: "saisi_par", width: 120 },
             ]} />
      {peutSaisir && (
        <Form form={form} layout="inline" onFinish={ajouter} className="equipement-evenement"
              initialValues={{ type_evenement: "Étalonnage", date_evenement: dayjs() }}>
          <Form.Item name="type_evenement"><Select style={{ width: 140 }} options={TYPES.map((t) => ({ value: t, label: t }))} /></Form.Item>
          <Form.Item name="date_evenement" rules={[{ required: true, message: "Date" }]}>
            <DatePicker format="DD/MM/YYYY" disabledDate={(d) => d && d > dayjs().endOf("day")} />
          </Form.Item>
          {(type === "Étalonnage" || type === "Vérification") && (
            <Form.Item name="resultat" rules={[{ required: true, message: "Résultat" }]}>
              <Select style={{ width: 140 }} placeholder="Résultat"
                      options={["Conforme", "Non conforme"].map((r) => ({ value: r, label: r }))} />
            </Form.Item>
          )}
          <Form.Item name="description" style={{ flex: 1, minWidth: 200 }}><Input placeholder="Description" /></Form.Item>
          <Button type="primary" htmlType="submit">Ajouter</Button>
        </Form>
      )}
    </div>
  );
}

export default function Equipements({ user }) {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const [rows, setRows] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState(null);
  const [edition, setEdition] = useState(null);   // null : fermé ; {} : nouveau ; objet : modification
  const responsable = estResponsable(user.role);

  const charger = () => {
    setChargement(true);
    return api.equipements()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => { charger(); }, []);

  const ouvrir = (eq) => {
    setEdition(eq || {});
    form.setFieldsValue(eq
      ? { ...eq, ...Object.fromEntries(DATES.map((k) => [k, eq[k] ? dayjs(eq[k]) : null])) }
      : { actif: true, section: undefined });
  };
  const enregistrer = async (v) => {
    const body = { ...v, ...Object.fromEntries(DATES.map((k) => [k, v[k] ? v[k].format(FORMAT_API) : null])),
                   section: v.section || null };
    try {
      if (edition?.id) await api.modifierEquipement(edition.id, body);
      else await api.creerEquipement(body);
      message.success(edition?.id ? "Équipement modifié." : "Équipement ajouté.");
      setEdition(null);
      form.resetFields();
      charger();
    } catch (e) { message.error(e.message); }
  };

  // Suppression (admin) : refusée par le serveur si l'équipement a un historique ou est cité dans une fiche
  const supprimer = () => modal.confirm({
    title: `Supprimer l'équipement ${edition.code} ?`,
    content: "Un équipement avec un historique ou utilisé dans une fiche ne peut pas être supprimé : désactivez-le.",
    okText: "Supprimer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { await api.supprimerEquipement(edition.id); message.success("Équipement supprimé."); setEdition(null); form.resetFields(); charger(); }
      catch (e) { message.error(e.message); }
    },
  });

  const colonnes = [
    { title: "Code", dataIndex: "code", width: 110, render: (v) => <span className="mono">{v}</span>,
      sorter: (a, b) => a.code.localeCompare(b.code, "fr", { numeric: true }) },
    { title: "Désignation", dataIndex: "designation", ellipsis: true },
    { title: "Section", dataIndex: "section", width: 90, render: (s) => (s ? <SectionTag code={s} /> : <Tag>Commun</Tag>) },
    { title: "Emplacement", dataIndex: "emplacement", ellipsis: true, render: (v) => v || "—" },
    { title: "Prochain étalonnage", dataIndex: "prochain_etalonnage", width: 150,
      render: (v, r) => (r.jamais_etalonne ? <Typography.Text type="danger">Jamais étalonné</Typography.Text> : <span className="mono">{fmt(v)}</span>) },
    { title: "Prochaine vérification", dataIndex: "prochaine_verification", width: 160,
      render: (v, r) => (r.jamais_verifie ? <Typography.Text type="danger">Jamais vérifié</Typography.Text> : <span className="mono">{fmt(v)}</span>) },
    { title: "État", dataIndex: "statut_echeance", width: 140,
      filters: Object.entries(ECHEANCE).map(([value, e]) => ({ text: e.libelle, value })),
      onFilter: (v, r) => r.statut_echeance === v, render: (v) => <EcheanceTag statut={v} /> },
    ...(responsable ? [{
      title: "", key: "actions", width: 90, align: "right",
      render: (_, r) => <Button type="link" size="small" className="btn-lien" onClick={() => ouvrir(r)}>Modifier</Button>,
    }] : []),
  ];

  return (
    <>
      <Flex justify="space-between" align="flex-start" className="page-entete">
        <div>
          <Typography.Title level={4} className="page-titre">Équipements</Typography.Title>
          <Typography.Text type="secondary">Inventaire, étalonnages, vérifications et maintenance.</Typography.Text>
        </div>
        {responsable && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouvel équipement</Button>}
      </Flex>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />

      <Table size="small" rowKey="id" columns={colonnes} dataSource={rows} loading={chargement}
             pagination={rows.length > 50 ? { pageSize: 50 } : false}
             expandable={{ expandedRowRender: (eq) => (
               <Historique eq={eq} peutSaisir={user.role !== "user"} onChange={charger} />) }}
             locale={{ emptyText: <Vide texte="Aucun équipement."
               action={responsable && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouvel équipement</Button>} /> }} />

      <Modal title={edition?.id ? `Modifier ${edition.code}` : "Nouvel équipement"} open={edition !== null}
             okText="Enregistrer" cancelText="Annuler" onOk={() => form.submit()} width={760}
             onCancel={() => { setEdition(null); form.resetFields(); }} forceRender>
        <Form form={form} layout="vertical" onFinish={enregistrer} className="form-dense">
          <Row gutter={16}>
            <Col xs={24} sm={8}><Form.Item label="Code d'inventaire" name="code" rules={[{ required: true, whitespace: true, message: "Code obligatoire" }]}><Input /></Form.Item></Col>
            <Col xs={24} sm={16}><Form.Item label="Désignation" name="designation" rules={[{ required: true, whitespace: true, message: "Désignation obligatoire" }]}><Input /></Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="N° de série" name="numero_serie"><Input /></Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="Section" name="section">
              <Select allowClear placeholder="Commun" options={["SMA", "SCHA", "SSA"].map((s) => ({ value: s, label: s }))} />
            </Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="Emplacement" name="emplacement"><Input /></Form.Item></Col>
            <Col xs={12} sm={6}><Form.Item label="Dernier étalonnage" name="date_dernier_etalonnage"><DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} /></Form.Item></Col>
            <Col xs={12} sm={6}><Form.Item label="Périodicité (mois)" name="periodicite_etalonnage_mois" tooltip="Vide = non soumis à étalonnage"><InputNumber min={1} max={240} style={{ width: "100%" }} /></Form.Item></Col>
            <Col xs={12} sm={6}><Form.Item label="Dernière vérification" name="date_derniere_verification"><DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} /></Form.Item></Col>
            <Col xs={12} sm={6}><Form.Item label="Périodicité (mois)" name="periodicite_verification_mois"><InputNumber min={1} max={240} style={{ width: "100%" }} /></Form.Item></Col>
            <Col xs={24} sm={18}><Form.Item label="Observations" name="observations"><Input /></Form.Item></Col>
            <Col xs={24} sm={6}><Form.Item label="Actif" name="actif" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
          {edition?.id && user.role === "admin" && (
            <Flex justify="flex-end"><Button danger size="small" onClick={supprimer}>Supprimer l'équipement</Button></Flex>
          )}
        </Form>
      </Modal>
    </>
  );
}
