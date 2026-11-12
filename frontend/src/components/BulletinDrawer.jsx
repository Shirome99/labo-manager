import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert, App, Button, Descriptions, Drawer, Flex, Form, Input, InputNumber, Modal, Radio, Select, Space, Spin,
  Table, Tag, Typography,
} from "antd";
import { FilePdfOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import BoutonFichier from "./BoutonFichier";
import Encaissements from "./Encaissements";
import { ErreurChargement } from "./etats";
import { ROLES_FACTURATION, SectionTag, estResponsable, formatDH } from "./ui";

const arr = (d) => (Array.isArray(d) ? d : []);
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("fr-FR") : "—");

export const STATUT_FACTURE_COULEUR = { brouillon: "default", "émis": "green", "annulé": "red" };

/** Tag de statut d'un bulletin / avoir. */
export function FactureTag({ f }) {
  if (!f) return null;
  return (
    <Space size={4}>
      {f.type === "avoir" && <Tag color="purple" style={{ marginInlineEnd: 0 }}>Avoir</Tag>}
      <Tag color={STATUT_FACTURE_COULEUR[f.statut]} style={{ marginInlineEnd: 0 }}>
        {f.statut === "émis" ? "Émis" : f.statut === "brouillon" ? "Brouillon" : "Annulé"}
      </Tag>
    </Space>
  );
}

/**
 * Tiroir d'un bulletin (ou d'un avoir) : échantillons, lignes, totaux, avoirs liés.
 * Brouillon : échantillons modifiables, émission, abandon. Émis : PDF archivé, avoir (responsables).
 * props : id, user, onFermer, onChange (après une action)
 */
export default function BulletinDrawer({ id, user, onFermer, onChange }) {
  const { message, modal } = App.useApp();
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [avoir, setAvoir] = useState(false);
  const [ouvert, setOuvert] = useState(id);          // un avoir créé s'ouvre à la place
  const peutFacturer = ROLES_FACTURATION.includes(user.role);

  const charger = () => api.facture(ouvert).then(setF).catch((e) => setErr(e.message));
  useEffect(() => { setOuvert(id); }, [id]);
  useEffect(() => { if (ouvert) { setF(null); setErr(null); charger(); } }, [ouvert]); // eslint-disable-line react-hooks/exhaustive-deps

  const agir = async (fn, texte) => {
    setEnvoi(true);
    try { const r = await fn(); setF(r); message.success(texte(r)); onChange?.(); }
    catch (e) { message.error(e.message); } finally { setEnvoi(false); }
  };

  const emettre = () => modal.confirm({
    title: "Émettre le bulletin ?",
    content: "Un numéro définitif lui est attribué et le PDF est archivé. Il ne pourra plus être modifié (correction par avoir).",
    okText: "Émettre", cancelText: "Annuler",
    onOk: () => agir(() => api.emettreFacture(f.id), (r) => `Bulletin ${r.numero} émis.`),
  });
  const abandonner = () => modal.confirm({
    title: "Abandonner ce brouillon ?", okText: "Abandonner", okButtonProps: { danger: true }, cancelText: "Retour",
    onOk: () => agir(() => api.annulerFacture(f.id), () => "Brouillon abandonné."),
  });

  const brouillon = f?.statut === "brouillon";
  const colonnes = [
    { title: "Échantillon", dataIndex: "num_echantillon", width: 130, render: (v) => (v ? <span className="mono">{v}</span> : "—") },
    { title: "Section", dataIndex: "section", width: 70, render: (v) => (v ? <SectionTag code={v} /> : <Tag>Divers</Tag>) },
    { title: "Analyse / libellé", dataIndex: "analyse" },
    { title: "Qté", dataIndex: "quantite", width: 60, align: "right", render: (v) => Number(v).toLocaleString("fr-FR") },
    {
      title: "Prix unitaire", dataIndex: "prix_unitaire", width: 120, align: "right",
      render: (v) => (v === null || v === undefined ? <Tag color="red">Prix à renseigner</Tag> : <span className="mono">{formatDH(Math.abs(v))}</span>),
    },
    { title: "Montant", dataIndex: "montant", width: 120, align: "right", render: (v) => <span className="mono">{formatDH(v)}</span> },
  ];

  const titre = f ? `${f.type === "avoir" ? "Avoir" : "Bulletin"} ${f.numero || "(brouillon)"}` : "Bulletin";

  return (
    <Drawer open={Boolean(id)} onClose={onFermer} size={860} title={<Space>{titre}<FactureTag f={f} /></Space>}
            extra={f && (
              <Space wrap>
                <BoutonFichier icon={<FilePdfOutlined />} url={api.urlPdfFacture(f.id)}>
                  {brouillon ? "Aperçu PDF" : "PDF"}
                </BoutonFichier>
                {brouillon && peutFacturer && <Button onClick={abandonner} disabled={envoi}>Abandonner</Button>}
                {brouillon && peutFacturer && <Button type="primary" onClick={emettre} loading={envoi}>Émettre</Button>}
                {f.statut === "émis" && f.type === "facture" && estResponsable(user.role) && (
                  <Button danger onClick={() => setAvoir(true)}>Faire un avoir</Button>
                )}
              </Space>
            )}>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />
      {!f && !err && <Flex justify="center" style={{ padding: 32 }}><Spin /></Flex>}
      {f && (
        <>
          {f.type === "avoir" && f.origine && (
            <Alert type="info" showIcon style={{ marginBottom: 12 }}
                   title={<>Annule {Math.abs(Number(f.total_ttc)) < Number(f.origine.total_ttc) ? "partiellement " : ""}le bulletin{" "}
                     <Button type="link" size="small" className="btn-lien" onClick={() => setOuvert(f.origine.id)}>{f.origine.numero}</Button>
                     {" "}— motif : {f.motif}</>} />
          )}
          {brouillon && arr(f.sans_prix).length > 0 && (
            <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                   title={`Prix à renseigner avant l'émission : ${f.sans_prix.join(", ")}`} />
          )}
          <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }} items={[
            { label: "Client", children: f.client_nom || "Non renseigné" },
            { label: "Adresse", children: f.client_adresse || "—" },
            { label: "Date d'émission", children: fmtDate(f.date_emission) },
            { label: "Émis par", children: f.emise_par || "—" },
            ...(f.sha256 ? [{ label: "Empreinte SHA-256", span: 2,
                              children: <Typography.Text className="mono" copyable={{ text: f.sha256 }}>{f.sha256.slice(0, 16)}…</Typography.Text> }] : []),
          ]} />
          <EchantillonsBulletin f={f} modifiable={brouillon && peutFacturer} onModifie={setF} />
          <Table size="small" rowKey={(l) => `${l.id}`} columns={colonnes} dataSource={arr(f.lignes)} pagination={false}
                 style={{ marginTop: 12 }} locale={{ emptyText: "Aucune ligne à facturer." }} />
          <Flex justify="flex-end" style={{ marginTop: 12 }}>
            <Descriptions size="small" column={1} bordered style={{ minWidth: 320 }} items={[
              ...(Number(f.taux_tva) > 0 ? [
                { label: "Total HT", children: <span className="mono">{formatDH(f.total_ht)}</span> },
                { label: `TVA ${Number(f.taux_tva).toLocaleString("fr-FR")} %`, children: <span className="mono">{formatDH(f.montant_tva)}</span> },
              ] : []),
              { label: Number(f.taux_tva) > 0 ? "Total TTC" : "Total", children: <b className="mono">{formatDH(f.total_ttc)}</b> },
              ...(arr(f.avoirs).length ? [
                { label: "Avoirs", children: <span className="mono">{formatDH(f.total_avoirs)}</span> },
                { label: "Net à payer", children: <b className="mono">{formatDH(f.net)}</b> },
              ] : []),
            ]} />
          </Flex>
          {f.type === "facture" && f.statut === "émis" && (
            <Encaissements f={f} user={user} onMaj={(c) => { setF(c); onChange?.(); }} />
          )}
          {arr(f.avoirs).length > 0 && (
            <>
              <Typography.Title level={5} style={{ marginTop: 16 }}>Avoirs</Typography.Title>
              <Table size="small" rowKey="id" pagination={false} dataSource={f.avoirs} columns={[
                { title: "N°", dataIndex: "numero", render: (v, a) => <Button type="link" size="small" className="btn-lien" onClick={() => setOuvert(a.id)}>{v}</Button> },
                { title: "Date", dataIndex: "date_emission", width: 110, render: fmtDate },
                { title: "Motif", dataIndex: "motif" },
                { title: "Montant", dataIndex: "total_ttc", width: 120, align: "right", render: (v) => <span className="mono">{formatDH(v)}</span> },
              ]} />
            </>
          )}
        </>
      )}
      {avoir && f && (
        <AvoirModal f={f} onFermer={() => setAvoir(false)}
                    onFait={(a) => { setAvoir(false); onChange?.(); setOuvert(a.id); message.success(`Avoir ${a.numero} émis.`); }} />
      )}
    </Drawer>
  );
}

function EchantillonsBulletin({ f, modifiable, onModifie }) {
  const { message } = App.useApp();
  const [options, setOptions] = useState([]);
  const [saisie, setSaisie] = useState("");

  useEffect(() => {
    if (!modifiable) return undefined;
    const minuteur = setTimeout(() => {
      api.echantillons({ q: saisie.trim() || f.client_nom || "", page: 1, taille: 30 })
        .then((d) => setOptions(arr(d?.lignes).map((e) => ({ value: e.num_echantillon, label: `${e.num_echantillon} — ${e.nature || ""}` }))))
        .catch(() => setOptions([]));
    }, 300);
    return () => clearTimeout(minuteur);
  }, [saisie, modifiable]); // eslint-disable-line react-hooks/exhaustive-deps

  const changer = async (nums) => {
    if (!nums.length) return;
    try { onModifie(await api.modifierFacture(f.id, { echantillons: nums })); }
    catch (e) { message.error(e.message); }
  };

  if (!modifiable) {
    return (
      <Space size={6} wrap>
        <Typography.Text type="secondary">Échantillons :</Typography.Text>
        {arr(f.echantillons).map((n) => <Link key={n} to={`/echantillons/detail/${encodeURIComponent(n)}`} className="mono">{n}</Link>)}
      </Space>
    );
  }
  return (
    <Form.Item label="Échantillons (même client)" style={{ marginBottom: 0 }}
               extra="Ajoutez d'autres échantillons du même client pour les regrouper dans ce bulletin.">
      <Select mode="multiple" value={arr(f.echantillons)} onChange={changer} options={options}
              showSearch={{ filterOption: false, onSearch: setSaisie }} style={{ width: "100%" }} />
    </Form.Item>
  );
}

function AvoirModal({ f, onFermer, onFait }) {
  const [form] = Form.useForm();
  const [mode, setMode] = useState("lignes");
  const [choix, setChoix] = useState([]);
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const enregistrer = async (v) => {
    setErr(null);
    if (mode === "lignes" && !choix.length) { setErr("Choisissez au moins une ligne à annuler."); return; }
    setEnvoi(true);
    try {
      onFait(await api.creerAvoir(f.id, mode === "lignes" ? { motif: v.motif, details: choix } : { motif: v.motif, montant: v.montant }));
    } catch (e) { setErr(e.message); } finally { setEnvoi(false); }
  };

  return (
    <Modal open title={`Avoir sur le bulletin ${f.numero}`} okText="Émettre l'avoir" okButtonProps={{ danger: true }}
           cancelText="Annuler" onOk={() => form.submit()} onCancel={onFermer} confirmLoading={envoi} width={680} destroyOnHidden>
      {err && <Alert type="error" showIcon title={err} style={{ marginBottom: 12 }} />}
      <Typography.Paragraph type="secondary">
        L'avoir est émis aussitôt (numéro, PDF archivé). Les lignes annulées redeviennent modifiables sur
        l'échantillon : corrigez-les puis faites un nouveau bulletin, ou retirez-les.
      </Typography.Paragraph>
      <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)} optionType="button" style={{ marginBottom: 12 }}
                   options={[{ value: "lignes", label: "Lignes à annuler" }, { value: "montant", label: "Montant" }]} />
      <Form form={form} layout="vertical" className="form-dense" onFinish={enregistrer}>
        {mode === "lignes" ? (
          <Table size="small" rowKey="id" pagination={false} dataSource={arr(f.lignes)}
                 rowSelection={{ selectedRowKeys: choix, onChange: setChoix }}
                 columns={[
                   { title: "Échantillon", dataIndex: "num_echantillon", render: (v) => v || "—" },
                   { title: "Libellé", dataIndex: "analyse" },
                   { title: "Montant", dataIndex: "montant", align: "right", render: (v) => formatDH(v) },
                 ]} style={{ marginBottom: 12 }} />
        ) : (
          <Form.Item label="Montant à annuler (HT)" name="montant" rules={[{ required: true, message: "Saisissez le montant" }]}>
            <InputNumber min={0.01} max={Number(f.net)} precision={2} decimalSeparator="," style={{ width: 200 }} suffix="DH" />
          </Form.Item>
        )}
        <Form.Item label="Motif" name="motif" rules={[{ required: true, whitespace: true, message: "Le motif de l'avoir est obligatoire" }]}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
