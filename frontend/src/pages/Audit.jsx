import { useEffect, useState } from "react";
import {
  Alert, Button, Card, Col, DatePicker, Form, Input, Row, Select, Space, Switch, Table, Tag, Typography,
} from "antd";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";

const FORMAT_API = "YYYY-MM-DD";
const COULEUR_OP = { INSERT: "green", UPDATE: "blue", DELETE: "red" };
const LIBELLE_OP = { INSERT: "Création", UPDATE: "Modification", DELETE: "Suppression" };
const PAR_PAGE = 50;

const affichage = (v) => {
  if (v === undefined) return <Typography.Text type="secondary">—</Typography.Text>;
  if (v === null) return <Typography.Text type="secondary">vide</Typography.Text>;
  return typeof v === "object" ? JSON.stringify(v) : String(v);
};

// Comparaison avant / après d'une ligne du journal
function Comparaison({ ligne }) {
  const [modifsSeules, setModifsSeules] = useState(ligne.operation === "UPDATE");
  const avant = ligne.avant || {};
  const apres = ligne.apres || {};
  const champs = [...new Set([...Object.keys(avant), ...Object.keys(apres)])].sort();
  const change = (c) => JSON.stringify(avant[c]) !== JSON.stringify(apres[c]);
  const lignes = champs
    .filter((c) => !modifsSeules || change(c))
    .map((c) => ({ champ: c, avant: avant[c], apres: apres[c], change: ligne.operation === "UPDATE" && change(c) }));

  return (
    <div className="audit-comparaison">
      {ligne.operation === "UPDATE" && (
        <Space size={8} style={{ marginBottom: 8 }}>
          <Switch size="small" checked={modifsSeules} onChange={setModifsSeules} />
          <Typography.Text type="secondary">Champs modifiés seulement</Typography.Text>
        </Space>
      )}
      <Table
        size="small"
        rowKey="champ"
        pagination={false}
        dataSource={lignes}
        rowClassName={(r) => (r.change ? "audit-change" : "")}
        columns={[
          { title: "Champ", dataIndex: "champ", key: "champ", width: 220, render: (v) => <span className="mono">{v}</span> },
          ...(ligne.operation !== "INSERT"
            ? [{ title: "Avant", key: "avant", render: (_, r) => affichage(ligne.avant ? r.avant : undefined) }] : []),
          ...(ligne.operation !== "DELETE"
            ? [{ title: "Après", key: "apres", render: (_, r) => affichage(ligne.apres ? r.apres : undefined) }] : []),
        ]}
      />
    </div>
  );
}

export default function Audit() {
  const [form] = Form.useForm();
  const [tables, setTables] = useState([]);
  const [filtres, setFiltres] = useState({});
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ total: 0, lignes: [] });
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState(null);
  const [essai, setEssai] = useState(0);   // « Réessayer » relance le chargement

  useEffect(() => {
    api.auditTables().then((d) => setTables(Array.isArray(d) ? d : [])).catch(() => setTables([]));
  }, []);

  useEffect(() => {
    setChargement(true);
    setErr(null);
    api.journalAudit({ ...filtres, limite: PAR_PAGE, decalage: (page - 1) * PAR_PAGE })
      .then((d) => setData({ total: d?.total || 0, lignes: Array.isArray(d?.lignes) ? d.lignes : [] }))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  }, [filtres, page, essai]);

  const appliquer = ({ periode, ...v }) => {
    setPage(1);
    setFiltres({
      ...v,
      du: periode?.[0] ? periode[0].format(FORMAT_API) : "",
      au: periode?.[1] ? periode[1].format(FORMAT_API) : "",
    });
  };
  const effacer = () => { form.resetFields(); setPage(1); setFiltres({}); };

  const colonnes = [
    {
      title: "Date", dataIndex: "horodatage", key: "date", width: 160,
      render: (v) => <span className="mono">{new Date(v).toLocaleString("fr-FR")}</span>,
    },
    { title: "Table", dataIndex: "table_nom", key: "table", render: (v) => <span className="mono">{v}</span> },
    {
      title: "Opération", dataIndex: "operation", key: "op", width: 120,
      render: (v) => <Tag color={COULEUR_OP[v]}>{LIBELLE_OP[v] || v}</Tag>,
    },
    { title: "Clé", dataIndex: "cle", key: "cle", render: (v) => <span className="mono">{v || "—"}</span> },
    { title: "Échantillon", dataIndex: "num_echantillon", key: "num", render: (v) => <span className="mono">{v || "—"}</span> },
    {
      title: "Utilisateur", dataIndex: "utilisateur", key: "user",
      render: (v, r) => (
        <Space size={4}>
          <span>{v}</span>
          {r.source === "base" && <Tag color="orange">Hors application</Tag>}
        </Space>
      ),
    },
  ];

  return (
    <>
      <div className="page-entete">
        <Typography.Title level={4} className="page-titre">Journal d'audit</Typography.Title>
        <Typography.Text type="secondary">
          Toutes les écritures en base, y compris hors application. Le journal ne peut être ni modifié ni effacé.
        </Typography.Text>
      </div>

      <Card size="small" className="bloc">
        <Form form={form} layout="vertical" onFinish={appliquer} className="form-dense">
          <Row gutter={16}>
            <Col xs={24} sm={12} lg={5}>
              <Form.Item label="Table" name="table">
                <Select allowClear placeholder="Toutes" options={tables.map((t) => ({ value: t, label: t }))} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <Form.Item label="Opération" name="operation">
                <Select allowClear placeholder="Toutes"
                        options={Object.entries(LIBELLE_OP).map(([value, label]) => ({ value, label }))} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <Form.Item label="Utilisateur" name="utilisateur"><Input allowClear /></Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <Form.Item label="N° d'échantillon" name="num"><Input allowClear /></Form.Item>
            </Col>
            <Col xs={24} lg={7}>
              <Form.Item label="Période" name="periode">
                <DatePicker.RangePicker allowEmpty={[true, true]} format="DD/MM/YYYY"
                                        placeholder={["Du", "Au"]} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
          <Space>
            <Button type="primary" htmlType="submit">Filtrer</Button>
            <Button type="link" onClick={effacer}>Effacer les filtres</Button>
          </Space>
        </Form>
      </Card>

      <ErreurChargement message={err} onReessayer={() => setEssai((n) => n + 1)} />

      <Table
        size="small"
        rowKey="id"
        columns={colonnes}
        dataSource={data.lignes}
        loading={chargement}
        expandable={{ expandedRowRender: (l) => <Comparaison ligne={l} /> }}
        pagination={{
          current: page, pageSize: PAR_PAGE, total: data.total, showSizeChanger: false,
          showTotal: (t) => `${t} ligne${t > 1 ? "s" : ""}`, onChange: setPage,
        }}
        locale={{ emptyText: "Aucune écriture pour ces filtres." }}
      />
    </>
  );
}
