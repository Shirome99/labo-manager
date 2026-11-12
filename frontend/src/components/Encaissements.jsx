import { useState } from "react";
import {
  Alert, App, Button, Col, DatePicker, Descriptions, Flex, Form, Input, InputNumber, Modal, Row, Select, Space, Table,
  Tag, Tooltip, Typography,
} from "antd";
import { FilePdfOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { api } from "../api/client";
import BoutonFichier from "./BoutonFichier";
import { PaiementTag, ROLES_FACTURATION, estResponsable, formatDH } from "./ui";

const arr = (d) => (Array.isArray(d) ? d : []);
const MODES = ["espèces", "chèque", "virement", "autre"].map((m) => ({ value: m, label: m.charAt(0).toUpperCase() + m.slice(1) }));
export const TYPES_EXONERATION = ["contrôle officiel", "convention", "autre"].map((t) => ({ value: t, label: t.charAt(0).toUpperCase() + t.slice(1) }));
const fmtDate = (d) => (d ? dayjs(d).format("DD/MM/YYYY") : "—");

/**
 * Encaissements d'un bulletin émis (tâche 37) : statut, payé, reste, liste des encaissements (quittances),
 * encaisser (accueil, admin), annuler un encaissement, exonérer / annuler l'exonération (responsables).
 * props : f (contenu du bulletin), user, onMaj(contenu)
 */
/** Confirmation avec motif obligatoire (annulations) : demander(titre, async (motif) => …). */
export function useDemanderMotif() {
  const { message, modal } = App.useApp();
  return (titre, action) => {
    let motif = "";
    modal.confirm({
      title: titre,
      content: <Input.TextArea rows={2} placeholder="Motif (obligatoire)" onChange={(e) => { motif = e.target.value; }} />,
      okText: "Confirmer", okButtonProps: { danger: true }, cancelText: "Retour",
      onOk: async () => {
        if (!motif.trim()) { message.error("Le motif est obligatoire."); throw new Error("motif"); }
        await action(motif);
      },
    });
  };
}

export default function Encaissements({ f, user, onMaj }) {
  const { message } = App.useApp();
  const demanderMotif = useDemanderMotif();
  const [encaisser, setEncaisser] = useState(false);
  const [exonerer, setExonerer] = useState(false);
  const responsable = estResponsable(user.role);
  const peutEncaisser = ROLES_FACTURATION.includes(user.role) && f.statut_paiement !== "Exonéré" && Number(f.reste) > 0;

  const annulerPaiement = (p) => demanderMotif(`Annuler l'encaissement ${p.numero_quittance} (${formatDH(p.montant)}) ?`,
    async (motif) => {
      try { onMaj(await api.annulerPaiement(p.id, motif)); message.success("Encaissement annulé."); }
      catch (e) { message.error(e.message); throw e; }
    });

  const annulerExoneration = () => demanderMotif("Annuler l'exonération de ce bulletin ?", async (motif) => {
    try { onMaj(await api.annulerExoneration(f.exoneration.id, motif)); message.success("Exonération annulée."); }
    catch (e) { message.error(e.message); throw e; }
  });

  return (
    <>
      <Flex justify="space-between" align="center" wrap gap={8} style={{ marginTop: 16, marginBottom: 8 }}>
        <Space size={12} wrap>
          <Typography.Title level={5} style={{ margin: 0 }}>Paiement</Typography.Title>
          <PaiementTag statut={f.statut_paiement} />
          <Typography.Text>Payé : <b className="mono">{formatDH(f.paye)}</b></Typography.Text>
          <Typography.Text>Reste dû : <b className="mono">{formatDH(f.reste)}</b></Typography.Text>
          {Number(f.trop_percu) > 0 && <Tag color="orange">Trop-perçu {formatDH(f.trop_percu)}</Tag>}
        </Space>
        <Space size={8}>
          {responsable && !f.exoneration && f.statut_paiement !== "Avoir total" && (
            <Button onClick={() => setExonerer(true)}>Exonérer</Button>
          )}
          {peutEncaisser && <Button type="primary" onClick={() => setEncaisser(true)}>Encaisser</Button>}
        </Space>
      </Flex>
      {f.exoneration && (
        <Alert type="info" showIcon style={{ marginBottom: 8 }}
               title={`Exonéré (${f.exoneration.type}) le ${fmtDate(f.exoneration.accorde_le)} par ${f.exoneration.accorde_par} : ${f.exoneration.motif}`}
               action={responsable && <Button size="small" onClick={annulerExoneration}>Annuler l'exonération</Button>} />
      )}
      <Table size="small" rowKey="id" pagination={false} dataSource={arr(f.paiements)}
             locale={{ emptyText: "Aucun encaissement." }}
             rowClassName={(p) => (p.statut === "annulé" ? "ligne-annulee" : "")}
             columns={[
               { title: "Date", dataIndex: "date_paiement", width: 100, render: fmtDate },
               {
                 title: "Quittance", dataIndex: "numero_quittance", width: 150,
                 render: (v, p) => (
                   <BoutonFichier type="link" size="small" className="btn-lien mono" icon={<FilePdfOutlined />}
                                  url={api.urlQuittance(p.id)}>{v}</BoutonFichier>
                 ),
               },
               {
                 title: "Mode", dataIndex: "mode",
                 render: (v, p) => [v, p.reference && `n° ${p.reference}`, p.banque].filter(Boolean).join(" — "),
               },
               { title: "Encaissé par", dataIndex: "encaisse_par", width: 110 },
               {
                 title: "Montant", dataIndex: "montant", width: 120, align: "right",
                 render: (v, p) => (
                   <Space size={4}>
                     {p.trop_percu && <Tooltip title="Trop-perçu signalé"><Tag color="orange">TP</Tag></Tooltip>}
                     <span className="mono">{formatDH(v)}</span>
                   </Space>
                 ),
               },
               {
                 title: "", key: "statut", width: 150, align: "right",
                 render: (_, p) => (p.statut === "annulé"
                   ? <Tooltip title={`${p.motif_annulation} — ${p.annule_par}`}><Tag color="red">Annulé</Tag></Tooltip>
                   : responsable && (
                     <Button type="link" size="small" danger className="btn-lien" onClick={() => annulerPaiement(p)}>Annuler</Button>
                   )),
               },
             ]} />
      {encaisser && <EncaissementModal f={f} onFermer={() => setEncaisser(false)}
                                       onFait={(c) => { setEncaisser(false); onMaj(c); }} />}
      {exonerer && (
        <ExonerationModal titre={`Exonérer le bulletin ${f.numero}`}
                          envoyer={(v) => api.exonererFacture(f.id, v)}
                          onFermer={() => setExonerer(false)}
                          onFait={(c) => { setExonerer(false); onMaj(c); message.success("Bulletin exonéré."); }} />
      )}
    </>
  );
}

function EncaissementModal({ f, onFermer, onFait }) {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const mode = Form.useWatch("mode", form);

  const envoyer = async (body) => {
    const c = await api.encaisser(f.id, body);
    message.success(`Encaissement enregistré : quittance ${c.numero_quittance}.`);
    api.ouvrirFichier(api.urlQuittance(c.paiement_id)).catch((e) => message.error(e.message));
    onFait(c);
  };

  const enregistrer = async (v) => {
    setErr(null); setEnvoi(true);
    const body = { ...v, date_paiement: v.date_paiement.format("YYYY-MM-DD") };
    try { await envoyer(body); }
    catch (e) {
      if (/trop-perçu/.test(e.message)) {
        modal.confirm({
          title: "Enregistrer un trop-perçu ?", content: e.message, okText: "Enregistrer le trop-perçu", cancelText: "Corriger",
          onOk: async () => { try { await envoyer({ ...body, confirmer_trop_percu: true }); } catch (e2) { setErr(e2.message); } },
        });
      } else setErr(e.message);
    } finally { setEnvoi(false); }
  };

  return (
    <Modal open title={`Encaisser — bulletin ${f.numero}`} okText="Enregistrer" cancelText="Annuler"
           onOk={() => form.submit()} onCancel={onFermer} confirmLoading={envoi} width={620} destroyOnHidden>
      {err && <Alert type="error" showIcon title={err} style={{ marginBottom: 12 }} />}
      <Descriptions size="small" column={3} style={{ marginBottom: 12 }} items={[
        { label: "Net", children: formatDH(f.net) }, { label: "Payé", children: formatDH(f.paye) },
        { label: "Reste dû", children: <b>{formatDH(f.reste)}</b> },
      ]} />
      <Form form={form} layout="vertical" className="form-dense" onFinish={enregistrer}
            initialValues={{ date_paiement: dayjs(), montant: Number(f.reste) || null, mode: "espèces" }}>
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item label="Date" name="date_paiement" rules={[{ required: true, message: "Date requise" }]}>
              <DatePicker format="DD/MM/YYYY" allowClear={false} style={{ width: "100%" }}
                          disabledDate={(d) => d && d.isAfter(dayjs(), "day")} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Montant (DH)" name="montant" rules={[{ required: true, message: "Montant requis" }]}>
              <InputNumber min={0.01} precision={2} decimalSeparator="," style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Mode" name="mode" rules={[{ required: true, message: "Mode requis" }]}>
              <Select options={MODES} />
            </Form.Item>
          </Col>
          {["chèque", "virement"].includes(mode) && (
            <>
              <Col span={12}>
                <Form.Item label={mode === "chèque" ? "N° de chèque" : "Référence du virement"} name="reference"
                           rules={[{ required: true, whitespace: true, message: "Référence requise" }]}><Input /></Form.Item>
              </Col>
              <Col span={12}><Form.Item label="Banque" name="banque"><Input /></Form.Item></Col>
            </>
          )}
          <Col span={12}>
            <Form.Item label="N° de quittance" name="numero_quittance" extra="Vide : numéro automatique (Q-AAAA-NNNNN).">
              <Input placeholder="Carnet de la régie" />
            </Form.Item>
          </Col>
          <Col span={12}><Form.Item label="Observation" name="observation"><Input /></Form.Item></Col>
        </Row>
      </Form>
    </Modal>
  );
}

export function ExonerationModal({ titre, envoyer, onFermer, onFait }) {
  const [form] = Form.useForm();
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const enregistrer = async (v) => {
    setErr(null); setEnvoi(true);
    try { onFait(await envoyer(v)); } catch (e) { setErr(e.message); } finally { setEnvoi(false); }
  };
  return (
    <Modal open title={titre} okText="Exonérer" cancelText="Annuler" onOk={() => form.submit()} onCancel={onFermer}
           confirmLoading={envoi} destroyOnHidden>
      {err && <Alert type="error" showIcon title={err} style={{ marginBottom: 12 }} />}
      <Form form={form} layout="vertical" className="form-dense" onFinish={enregistrer} initialValues={{ type: "contrôle officiel" }}>
        <Form.Item label="Type d'exonération" name="type" rules={[{ required: true, message: "Choisissez le type" }]}>
          <Select options={TYPES_EXONERATION} />
        </Form.Item>
        <Form.Item label="Motif" name="motif" rules={[{ required: true, whitespace: true, message: "Le motif est obligatoire" }]}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
