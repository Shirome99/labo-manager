import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Alert, App, Button, Col, DatePicker, Flex, Form, Input, InputNumber, Modal, Row, Select, Switch, Table, Tabs, Tag,
  Typography,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement, Vide } from "../components/etats";
import { api } from "../api/client";
import { ROLE_SECTION, SectionTag, StatutTag, estResponsable } from "../components/ui";

const FORMAT_API = "YYYY-MM-DD";
const fmt = (d) => (d ? dayjs(d).format("DD/MM/YYYY") : "—");
const nf = (v) => (v === null || v === undefined ? "—" : new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(v));
const CATEGORIES = ["Réactif", "Milieu de culture", "Souche de référence", "Autre"];
const DATES = ["date_reception", "date_ouverture", "date_peremption"];
export const ETAT_LOT = {
  "ok": { couleur: "green", libelle: "Disponible" },
  "seuil bas": { couleur: "gold", libelle: "Stock bas" },
  "péremption proche": { couleur: "gold", libelle: "Péremption < 30 j" },
  "périmé": { couleur: "red", libelle: "Périmé" },
  "épuisé": { couleur: "default", libelle: "Épuisé" },
  "inactif": { couleur: "default", libelle: "Inactif" },
};
export function EtatLotTag({ etat }) {
  const e = ETAT_LOT[etat] || ETAT_LOT.ok;
  return <Tag color={e.couleur} style={{ marginInlineEnd: 0 }}>{e.libelle}</Tag>;
}

// Stock (mouvements) et utilisations d'un lot
function DetailLot({ lot, peutSaisir, onChange }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [mvts, setMvts] = useState(null);
  const [utils, setUtils] = useState(null);
  const charger = () => {
    api.mouvementsReactif(lot.id).then((d) => setMvts(Array.isArray(d) ? d : [])).catch(() => setMvts([]));
    api.utilisationsReactif(lot.id).then((d) => setUtils(Array.isArray(d) ? d : [])).catch(() => setUtils([]));
  };
  useEffect(() => { charger(); }, [lot.id, lot.quantite]); // eslint-disable-line react-hooks/exhaustive-deps
  const type = Form.useWatch("type_mouvement", form);
  const ajouter = async (v) => {
    try {
      await api.ajouterMouvementReactif(lot.id, { ...v, date_mouvement: v.date_mouvement.format(FORMAT_API) });
      message.success("Mouvement enregistré.");
      form.resetFields();
      onChange();
    } catch (e) { message.error(e.message); }
  };
  return (
    <Tabs size="small" items={[
      { key: "stock", label: `Stock (${nf(lot.quantite)} ${lot.unite})`, children: (
        <>
          <Table size="small" rowKey="id" pagination={false} loading={mvts === null} dataSource={mvts || []}
                 locale={{ emptyText: "Aucun mouvement." }}
                 columns={[
                   { title: "Date", dataIndex: "date_mouvement", width: 110, render: fmt },
                   { title: "Mouvement", dataIndex: "type_mouvement", width: 110 },
                   { title: "Quantité", dataIndex: "quantite", width: 100, align: "right", render: (v, r) => <span className="mono">{r.type_mouvement === "Sortie" ? "−" : r.type_mouvement === "Entrée" ? "+" : "= "}{nf(v)}</span> },
                   { title: "Stock après", dataIndex: "stock_apres", width: 110, align: "right", render: (v) => <span className="mono">{nf(v)}</span> },
                   { title: "Échantillon", dataIndex: "num_echantillon", width: 140, render: (v) => (v ? <Link className="mono" to={`/echantillons/detail/${encodeURIComponent(v)}`}>{v}</Link> : "—") },
                   { title: "Motif", dataIndex: "motif", render: (v) => v || "—" },
                   { title: "Saisi par", dataIndex: "saisi_par", width: 110 },
                 ]} />
          {peutSaisir && (
            <Form form={form} layout="inline" onFinish={ajouter} className="equipement-evenement"
                  initialValues={{ type_mouvement: "Sortie", date_mouvement: dayjs() }}>
              <Form.Item name="type_mouvement">
                <Select style={{ width: 130 }} options={["Sortie", "Entrée", "Ajustement"].map((t) => ({ value: t, label: t === "Ajustement" ? "Inventaire" : t }))} />
              </Form.Item>
              <Form.Item name="date_mouvement" rules={[{ required: true, message: "Date" }]}>
                <DatePicker format="DD/MM/YYYY" disabledDate={(d) => d && d > dayjs().endOf("day")} />
              </Form.Item>
              <Form.Item name="quantite" rules={[{ required: true, message: "Quantité" }]}>
                <InputNumber min={0} placeholder={type === "Ajustement" ? "Stock constaté" : "Quantité"} style={{ width: 140 }} suffix={lot.unite} />
              </Form.Item>
              <Form.Item name="num_echantillon"><Input placeholder="N° échantillon" style={{ width: 150 }} /></Form.Item>
              <Form.Item name="motif" style={{ flex: 1, minWidth: 160 }}><Input placeholder="Motif" /></Form.Item>
              <Button type="primary" htmlType="submit">Ajouter</Button>
            </Form>
          )}
        </>
      ) },
      { key: "utilisations", label: `Utilisations (${utils?.length ?? "…"})`, children: (
        <Table size="small" rowKey={(r) => `${r.section}-${r.num_echantillon}`} pagination={false} loading={utils === null}
               dataSource={utils || []} locale={{ emptyText: "Lot cité dans aucune fiche de traitement." }}
               columns={[
                 { title: "Échantillon", dataIndex: "num_echantillon", width: 150, render: (v) => <Link className="mono" to={`/echantillons/detail/${encodeURIComponent(v)}`}>{v}</Link> },
                 { title: "Section", dataIndex: "section", width: 90, render: (s) => <SectionTag code={s} /> },
                 { title: "Nature", dataIndex: "nature", render: (v) => v || "—" },
                 { title: "Mise en analyse", dataIndex: "date_mise_en_analyse", width: 130, render: fmt },
                 { title: "Statut", dataIndex: "statut", width: 120, render: (s) => <StatutTag statut={s} /> },
               ]} />
      ) },
    ]} />
  );
}

export default function Reactifs({ user }) {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const [rows, setRows] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState(null);
  const [edition, setEdition] = useState(null);
  const [ouverts, setOuverts] = useState([]);
  const [params] = useSearchParams();
  const sectionRole = ROLE_SECTION[user.role] || null;
  const responsable = estResponsable(user.role);
  const peutEcrire = (section) => responsable || (sectionRole && section === sectionRole);

  const charger = () => {
    setChargement(true);
    return api.reactifs()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => { charger(); }, []);
  useEffect(() => { const l = Number(params.get("lot")); if (l) setOuverts([l]); }, [params]);

  const ouvrir = (lot) => {
    setEdition(lot || {});
    form.setFieldsValue(lot
      ? { ...lot, ...Object.fromEntries(DATES.map((k) => [k, lot[k] ? dayjs(lot[k]) : null])) }
      : { actif: true, categorie: "Réactif", unite: "unité", section: sectionRole || undefined, date_reception: dayjs() });
  };
  const enregistrer = async (v) => {
    const body = { ...v, ...Object.fromEntries(DATES.map((k) => [k, v[k] ? v[k].format(FORMAT_API) : null])), section: v.section || null };
    try {
      if (edition?.id) await api.modifierLotReactif(edition.id, body);
      else await api.creerLotReactif(body);
      message.success(edition?.id ? "Lot modifié." : "Lot enregistré.");
      setEdition(null); form.resetFields(); charger();
    } catch (e) { message.error(e.message); }
  };

  // Suppression (admin) : refusée par le serveur si le lot a des mouvements ou est cité dans une fiche
  const supprimer = () => modal.confirm({
    title: `Supprimer le lot ${edition.code} ?`, content: "Un lot mouvementé ou utilisé ne peut pas être supprimé : désactivez-le.",
    okText: "Supprimer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { await api.supprimerLotReactif(edition.id); message.success("Lot supprimé."); setEdition(null); form.resetFields(); charger(); }
      catch (e) { message.error(e.message); }
    },
  });

  const colonnes = [
    { title: "Code", dataIndex: "code", width: 110, render: (v) => <span className="mono">{v}</span>, sorter: (a, b) => a.code.localeCompare(b.code) },
    { title: "Produit", dataIndex: "produit", ellipsis: true, sorter: (a, b) => a.produit.localeCompare(b.produit, "fr") },
    { title: "Catégorie", dataIndex: "categorie", width: 140, filters: CATEGORIES.map((c) => ({ text: c, value: c })), onFilter: (v, r) => r.categorie === v },
    { title: "N° de lot", dataIndex: "numero_lot", width: 120, render: (v) => <span className="mono">{v}</span> },
    { title: "Fournisseur", dataIndex: "fournisseur", width: 130, ellipsis: true, render: (v) => v || "—" },
    { title: "Section", dataIndex: "section", width: 90, render: (s) => (s ? <SectionTag code={s} /> : <Tag>Commun</Tag>) },
    { title: "Péremption", dataIndex: "date_peremption", width: 110, render: (v) => <span className="mono">{fmt(v)}</span>,
      sorter: (a, b) => a.date_peremption.localeCompare(b.date_peremption), defaultSortOrder: "ascend" },
    { title: "Stock", dataIndex: "quantite", width: 120, align: "right", render: (v, r) => <span className="mono">{nf(v)} {r.unite}</span> },
    { title: "État", dataIndex: "etat", width: 140, filters: Object.entries(ETAT_LOT).map(([value, e]) => ({ text: e.libelle, value })),
      onFilter: (v, r) => r.etat === v, render: (v) => <EtatLotTag etat={v} /> },
    { title: "", key: "actions", width: 80, align: "right",
      render: (_, r) => (peutEcrire(r.section) ? <Button type="link" size="small" className="btn-lien" onClick={() => ouvrir(r)}>Modifier</Button> : null) },
  ];

  return (
    <>
      <Flex justify="space-between" align="flex-start" className="page-entete">
        <div>
          <Typography.Title level={4} className="page-titre">Réactifs et milieux</Typography.Title>
          <Typography.Text type="secondary">Lots, péremptions, stock et traçabilité des lots utilisés par échantillon.</Typography.Text>
        </div>
        {(responsable || sectionRole) && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouveau lot</Button>}
      </Flex>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />
      <Table size="small" rowKey="id" columns={colonnes} dataSource={rows} loading={chargement}
             pagination={rows.length > 50 ? { pageSize: 50 } : false}
             expandable={{ expandedRowKeys: ouverts, onExpandedRowsChange: (k) => setOuverts([...k]),
                           expandedRowRender: (lot) => <DetailLot lot={lot} peutSaisir={peutEcrire(lot.section)} onChange={charger} /> }}
             locale={{ emptyText: <Vide texte="Aucun lot enregistré."
               action={(responsable || sectionRole) && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouveau lot</Button>} /> }} />

      <Modal title={edition?.id ? `Modifier ${edition.code}` : "Nouveau lot"} open={edition !== null} width={760}
             okText="Enregistrer" cancelText="Annuler" onOk={() => form.submit()} forceRender
             onCancel={() => { setEdition(null); form.resetFields(); }}>
        <Form form={form} layout="vertical" onFinish={enregistrer} className="form-dense">
          <Row gutter={16}>
            <Col xs={24} sm={16}><Form.Item label="Produit" name="produit" rules={[{ required: true, whitespace: true, message: "Produit obligatoire" }]}><Input /></Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="Catégorie" name="categorie"><Select options={CATEGORIES.map((c) => ({ value: c, label: c }))} /></Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="N° de lot (fournisseur)" name="numero_lot" rules={[{ required: true, whitespace: true, message: "N° de lot obligatoire" }]}><Input /></Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="Fournisseur" name="fournisseur"><Input /></Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="Section" name="section">
              <Select allowClear={!sectionRole} disabled={!!sectionRole} placeholder="Commun" options={["SMA", "SCHA", "SSA"].map((s) => ({ value: s, label: s }))} />
            </Form.Item></Col>
            <Col xs={12} sm={8}><Form.Item label="Réception" name="date_reception"><DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} /></Form.Item></Col>
            <Col xs={12} sm={8}><Form.Item label="Ouverture" name="date_ouverture"><DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} /></Form.Item></Col>
            <Col xs={12} sm={8}><Form.Item label="Péremption" name="date_peremption" rules={[{ required: true, message: "Date de péremption obligatoire" }]}><DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} /></Form.Item></Col>
            {!edition?.id && (
              <Col xs={12} sm={8}><Form.Item label="Quantité reçue" name="quantite_initiale" rules={[{ required: true, message: "Quantité obligatoire" }]}><InputNumber min={0} style={{ width: "100%" }} /></Form.Item></Col>
            )}
            <Col xs={12} sm={8}><Form.Item label="Unité" name="unite" rules={[{ required: true, whitespace: true, message: "Unité obligatoire" }]}><Input placeholder="flacon, boîte, g, mL…" /></Form.Item></Col>
            <Col xs={12} sm={8}><Form.Item label="Seuil d'alerte" name="seuil_alerte" tooltip="Alerte quand le stock est inférieur ou égal"><InputNumber min={0} style={{ width: "100%" }} /></Form.Item></Col>
            <Col xs={24} sm={12}><Form.Item label="Emplacement" name="emplacement"><Input /></Form.Item></Col>
            <Col xs={18} sm={8}><Form.Item label="Observations" name="observations"><Input /></Form.Item></Col>
            <Col xs={6} sm={4}><Form.Item label="Actif" name="actif" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
          {edition?.id && (
            <Flex justify="space-between" align="center" gap={8}>
              <Typography.Text type="secondary">Le stock se modifie par les mouvements (sortie, entrée, inventaire).</Typography.Text>
              {user.role === "admin" && <Button danger size="small" onClick={supprimer}>Supprimer le lot</Button>}
            </Flex>
          )}
        </Form>
      </Modal>
    </>
  );
}
