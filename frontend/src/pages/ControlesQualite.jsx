import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert, App, Button, Card, Col, DatePicker, Descriptions, Flex, Form, Input, InputNumber, Modal, Row, Select,
  Space, Switch, Table, Tag, Typography,
} from "antd";
import { CheckCircleOutlined, PlusOutlined, WarningOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement, Vide } from "../components/etats";
import { api } from "../api/client";
import CarteControle from "../components/CarteControle";
import { SectionTag, estResponsable } from "../components/ui";

const TYPES = ["Témoin positif", "Témoin négatif", "Blanc", "Duplicata", "Matériau de référence"];
const fmtN = (v) => (v == null ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 3 }));

function EtatSerie({ alerte }) {
  return alerte
    ? <Tag color="red" icon={<WarningOutlined />}>Alerte</Tag>
    : <Tag color="green" icon={<CheckCircleOutlined />}>Sous contrôle</Tag>;
}

// Détail d'une série : carte, statistiques, saisie, table des mesures
function DetailSerie({ serieId, user, onChange, onModifier }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [d, setD] = useState(null);
  const charger = () => api.serieCQ(serieId).then(setD).catch((e) => message.error(e.message));
  useEffect(() => { setD(null); charger(); }, [serieId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!d) return <Card size="small" loading />;
  const { serie, stats, points, alertes } = d;
  const quanti = serie.nature === "quantitatif";

  const ajouter = async (v) => {
    try {
      const r = await api.ajouterMesureCQ(serieId, { ...v, date_mesure: v.date_mesure.format("YYYY-MM-DD") });
      if (r.alerte_mesure?.length) message.warning(`Mesure enregistrée — alerte : ${r.alerte_mesure.join(" ; ")}`);
      else message.success("Mesure enregistrée.");
      form.resetFields(["valeur", "resultat", "commentaire"]);
      setD(r);
      onChange();
    } catch (e) { message.error(e.message); }
  };

  return (
    <Card size="small" className="bloc"
          title={<Space size={8}><SectionTag code={serie.section} />{serie.methode} — {serie.libelle}<EtatSerie alerte={d.alerte_active} /></Space>}
          extra={estResponsable(user.role) && <Button size="small" onClick={() => onModifier(serie)}>Modifier la série</Button>}>
      <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }} items={[
        { key: "t", label: "Type", children: serie.type_controle },
        ...(quanti ? [
          { key: "m", label: stats.reference ? "Moyenne (référence)" : "Moyenne (calculée)", children: `${fmtN(stats.moyenne)} ${serie.unite || ""}` },
          { key: "s", label: serie.ecart_type_ref != null ? "Écart-type (référence)" : "Écart-type (calculé)", children: fmtN(stats.sigma) },
          { key: "l", label: "Limites ±3σ", children: stats.lim_3s ? `${fmtN(stats.lim_3s[0])} à ${fmtN(stats.lim_3s[1])}` : "—" },
        ] : [{ key: "a", label: "Résultat attendu", children: serie.resultat_attendu || "—" }]),
      ]} />
      {quanti && <CarteControle points={points} stats={stats} unite={serie.unite} />}
      {alertes.length > 0 && (
        <Alert type="error" showIcon style={{ margin: "8px 0" }}
               title={`${alertes.length} mesure(s) en alerte`}
               description={alertes.slice(-5).map((a) => `${dayjs(a.date_mesure).format("DD/MM/YYYY")} : ${a.regles.join(" ; ")}`).join(" — ")} />
      )}

      {user.role !== "user" && serie.actif && (
        <Form form={form} layout="inline" onFinish={ajouter} className="cq-saisie" initialValues={{ date_mesure: dayjs() }}>
          <Form.Item name="date_mesure" rules={[{ required: true, message: "Date" }]}>
            <DatePicker format="DD/MM/YYYY" disabledDate={(x) => x && x > dayjs().endOf("day")} />
          </Form.Item>
          {quanti ? (
            <Form.Item name="valeur" rules={[{ required: true, message: "Valeur" }]}>
              <InputNumber placeholder={`Valeur${serie.unite ? " (" + serie.unite + ")" : ""}`} style={{ width: 160 }} />
            </Form.Item>
          ) : (
            <Form.Item name="resultat" rules={[{ required: true, whitespace: true, message: "Résultat" }]}>
              <Input placeholder="Résultat obtenu" style={{ width: 180 }} />
            </Form.Item>
          )}
          <Form.Item name="commentaire" style={{ flex: 1, minWidth: 180 }}><Input placeholder="Commentaire" /></Form.Item>
          <Button type="primary" htmlType="submit">Ajouter la mesure</Button>
        </Form>
      )}

      <Table size="small" rowKey="id" style={{ marginTop: 12 }} dataSource={[...points].reverse()}
             pagination={points.length > 20 ? { pageSize: 20 } : false}
             locale={{ emptyText: "Aucune mesure." }}
             columns={[
               { title: "Date", dataIndex: "date_mesure", width: 110, render: (v) => dayjs(v).format("DD/MM/YYYY") },
               quanti
                 ? { title: `Valeur${serie.unite ? " (" + serie.unite + ")" : ""}`, dataIndex: "valeur", width: 130, align: "right",
                     render: (v) => <span className="mono">{fmtN(v)}</span> }
                 : { title: "Résultat", dataIndex: "resultat", width: 160 },
               { title: "Contrôle", key: "zone", render: (_, p) => (p.regles.length
                 ? <Tag color="red" icon={<WarningOutlined />}>{p.regles.join(" ; ")}</Tag>
                 : p.zone === "2s" ? <Tag color="gold">Entre 2σ et 3σ</Tag> : <Tag color="green">Conforme</Tag>) },
               { title: "Commentaire", dataIndex: "commentaire", render: (v) => v || "" },
               { title: "Saisi par", dataIndex: "saisi_par", width: 110 },
             ]} />
    </Card>
  );
}

export default function ControlesQualite({ user }) {
  const { message } = App.useApp();
  const [params, setParams] = useSearchParams();
  const serieId = params.get("serie") ? Number(params.get("serie")) : null;
  const [series, setSeries] = useState(null);
  const [edition, setEdition] = useState(null);
  const [form] = Form.useForm();
  const nature = Form.useWatch("nature", form);
  const responsable = estResponsable(user.role);

  const [errSeries, setErrSeries] = useState(null);
  const charger = () => { setErrSeries(null); return api.seriesCQ().then((d) => setSeries(Array.isArray(d) ? d : [])).catch((e) => { setSeries([]); setErrSeries(e.message); }); };
  useEffect(() => { charger(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const ouvrir = (s) => {
    setEdition(s || {});
    form.setFieldsValue(s || { nature: "quantitatif", actif: true, type_controle: "Matériau de référence" });
  };
  const enregistrer = async (v) => {
    try {
      const r = edition?.id ? await api.modifierSerieCQ(edition.id, v) : await api.creerSerieCQ(v);
      message.success(edition?.id ? "Série modifiée." : "Série créée.");
      setEdition(null);
      form.resetFields();
      await charger();
      setParams({ serie: String(r.serie.id) });
    } catch (e) { message.error(e.message); }
  };

  return (
    <>
      <Flex justify="space-between" align="flex-start" className="page-entete">
        <div>
          <Typography.Title level={4} className="page-titre">Contrôles qualité internes</Typography.Title>
          <Typography.Text type="secondary">
            Cartes de contrôle : alerte hors ±3σ ou 7 points consécutifs du même côté de la moyenne.
          </Typography.Text>
        </div>
        {responsable && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouvelle série</Button>}
      </Flex>

      <ErreurChargement message={errSeries} onReessayer={charger} />
      <Table size="small" rowKey="id" className="bloc" loading={series === null} dataSource={series || []}
             pagination={false} locale={{ emptyText: <Vide texte="Aucune série de contrôle."
               action={responsable && <Button type="primary" icon={<PlusOutlined />} onClick={() => ouvrir(null)}>Nouvelle série</Button>} /> }}
             rowClassName={(s) => (s.id === serieId ? "ligne-edition" : "cq-ligne")}
             onRow={(s) => ({ onClick: () => setParams({ serie: String(s.id) }) })}
             columns={[
               { title: "Section", dataIndex: "section", width: 80, render: (s) => <SectionTag code={s} /> },
               { title: "Méthode", dataIndex: "methode" },
               { title: "Contrôle", dataIndex: "libelle" },
               { title: "Type", dataIndex: "type_controle", width: 170 },
               { title: "Mesures", dataIndex: "n_mesures", width: 90, align: "right" },
               { title: "Dernière", dataIndex: "derniere_mesure", width: 110, render: (v) => (v ? dayjs(v).format("DD/MM/YYYY") : "—") },
               { title: "État", key: "etat", width: 140,
                 render: (_, s) => (s.actif ? <EtatSerie alerte={s.alerte_active} /> : <Tag>Inactive</Tag>) },
             ]} />

      {serieId && <DetailSerie key={serieId} serieId={serieId} user={user} onChange={charger} onModifier={ouvrir} />}

      <Modal title={edition?.id ? "Modifier la série" : "Nouvelle série de contrôle"} open={edition !== null}
             okText="Enregistrer" cancelText="Annuler" onOk={() => form.submit()} width={760} forceRender
             onCancel={() => { setEdition(null); form.resetFields(); }}>
        <Form form={form} layout="vertical" onFinish={enregistrer} className="form-dense">
          <Row gutter={16}>
            <Col xs={24} sm={8}><Form.Item label="Section" name="section" rules={[{ required: true, message: "Section" }]}>
              <Select options={["SMA", "SCHA", "SSA"].map((s) => ({ value: s, label: s }))} />
            </Form.Item></Col>
            <Col xs={24} sm={16}><Form.Item label="Méthode" name="methode" rules={[{ required: true, whitespace: true, message: "Méthode" }]}><Input /></Form.Item></Col>
            <Col xs={24} sm={12}><Form.Item label="Contrôle (libellé)" name="libelle" rules={[{ required: true, whitespace: true, message: "Libellé" }]}><Input placeholder="ex. MRC lait en poudre, lot 23-118" /></Form.Item></Col>
            <Col xs={24} sm={12}><Form.Item label="Type" name="type_controle" rules={[{ required: true }]}>
              <Select options={TYPES.map((t) => ({ value: t, label: t }))} />
            </Form.Item></Col>
            <Col xs={24} sm={8}><Form.Item label="Nature" name="nature">
              <Select options={[{ value: "quantitatif", label: "Quantitatif (carte)" }, { value: "qualitatif", label: "Qualitatif" }]} />
            </Form.Item></Col>
            {nature !== "qualitatif" ? (
              <>
                <Col xs={24} sm={4}><Form.Item label="Unité" name="unite"><Input /></Form.Item></Col>
                <Col xs={12} sm={6}><Form.Item label="Moyenne de référence" name="moyenne_ref" tooltip="Vide = calculée sur les mesures"><InputNumber style={{ width: "100%" }} /></Form.Item></Col>
                <Col xs={12} sm={6}><Form.Item label="Écart-type de référence" name="ecart_type_ref" tooltip="Vide = calculé sur les mesures"><InputNumber min={0} style={{ width: "100%" }} /></Form.Item></Col>
              </>
            ) : (
              <Col xs={24} sm={16}><Form.Item label="Résultat attendu" name="resultat_attendu" rules={[{ required: true, whitespace: true, message: "Résultat attendu" }]}><Input placeholder="ex. Positif" /></Form.Item></Col>
            )}
            <Col xs={24} sm={6}><Form.Item label="Active" name="actif" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </>
  );
}
