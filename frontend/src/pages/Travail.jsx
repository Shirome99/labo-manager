import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Card, Col, Empty, Row, Statistic, Table, Tag, Typography } from "antd";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";
import { PaiementTag, SectionTag, StatutTag } from "../components/ui";

const COULEUR_MOTIF = {
  renvoyee: "volcano", retard: "red", recu: "blue", en_cours: "default", a_valider: "gold", a_emettre: "green",
};
const TITRES = {
  analyste: "Échantillons à traiter dans votre section, par priorité.",
  responsable: "Fiches à valider, puis rapports à émettre.",
  suivi: "Échantillons en retard, toutes sections (suivi).",
};
const fmt = (d) => (d ? String(d).slice(0, 10) : "—");

export default function Travail() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const [essai, setEssai] = useState(0);   // « Réessayer » relance le chargement
  useEffect(() => {
    setErr(null);
    api.travail().then(setData).catch((e) => setErr(e.message));
  }, [essai]);

  const items = Array.isArray(data?.items) ? data.items : [];
  const compteurs = Object.entries(data?.compteurs || {});

  const colonnes = [
    {
      title: "Priorité", dataIndex: "libelle", key: "motif", width: 170,
      render: (v, r) => <Tag color={COULEUR_MOTIF[r.motif]}>{v}</Tag>,
    },
    {
      title: "N° Échantillon", dataIndex: "num", key: "num",
      render: (v, r) => <Link className="mono cell-num" to={r.lien}>{v}</Link>,
    },
    { title: "Section", dataIndex: "section", key: "section", width: 90, render: (s) => <SectionTag code={s} /> },
    { title: "Nature", dataIndex: "nature", key: "nature", ellipsis: true, render: (v) => v || "—" },
    { title: "Réception", dataIndex: "date_reception", key: "date", width: 110, render: (v) => <span className="mono cell-date">{fmt(v)}</span> },
    { title: "Statut", dataIndex: "statut", key: "statut", width: 120, render: (v) => <StatutTag statut={v} /> },
    { title: "Paiement", dataIndex: "payement", key: "paiement", width: 140, render: (v) => <PaiementTag statut={v} /> },
    { title: "Détail", dataIndex: "detail", key: "detail", ellipsis: true, render: (v) => v || "" },
    {
      title: "", key: "ouvrir", align: "right", width: 90,
      render: (_, r) => <Button size="small" type="primary" onClick={() => navigate(r.lien)}>Ouvrir</Button>,
    },
  ];

  return (
    <>
      <div className="page-entete">
        <Typography.Title level={4} className="page-titre">Mon travail</Typography.Title>
        <Typography.Text type="secondary">{TITRES[data?.vue] || ""}</Typography.Text>
      </div>
      <ErreurChargement message={err} onReessayer={() => setEssai((n) => n + 1)} />

      {compteurs.length > 0 && (
        <Row gutter={[16, 16]} className="bloc">
          {compteurs.map(([motif, n]) => (
            <Col xs={12} md={6} key={motif}>
              <Card size="small">
                <Statistic title={items.find((x) => x.motif === motif)?.libelle || motif} value={n} />
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Table
        size="small"
        rowKey="num"
        columns={colonnes}
        dataSource={items}
        loading={data === null && !err}
        pagination={items.length > 50 ? { pageSize: 50 } : false}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Rien à traiter." /> }}
      />
    </>
  );
}
