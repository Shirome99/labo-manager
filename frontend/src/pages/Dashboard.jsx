import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Alert, Button, Card, Col, Empty, Flex, Progress, Row, Space, Spin, Statistic, Table, Tag, Tooltip, Typography,
} from "antd";
import { PlusOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";
import { PaiementTag, SECTIONS, STATUTS, STATUT_COULEUR, SectionTag, StatutTag } from "../components/ui";

const arr = (x) => (Array.isArray(x) ? x : []);
const lienListe = (params) => `/echantillons?${new URLSearchParams(params).toString()}`;
const lienDetail = (num) => `/echantillons/detail/${encodeURIComponent(num)}`;
// Couleur des barres de répartition (mêmes teintes que les statuts)
const BARRE = { "Reçu": "#8B949E", "En cours": "#0969DA", "À valider": "#9A6700", "Validé": "#00875A", "Rapport émis": "#006644" };

const vide = (texte) => <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={texte} />;

// Petite liste cliquable (à valider / retards / récents)
function ListeEchantillons({ titre, lignes, texteVide, lienTout, meta }) {
  return (
    <Card size="small" title={titre} className="bloc"
          extra={lienTout && <Link to={lienTout}>Tout voir</Link>}>
      {lignes === null ? <Flex justify="center" style={{ padding: 16 }}><Spin /></Flex>
        : lignes.length === 0 ? vide(texteVide)
        : lignes.map((e) => (
          <Flex key={e.num_echantillon} justify="space-between" align="center" gap={8} className="dash-item">
            <Link to={lienDetail(e.num_echantillon)} className="dash-ligne">
              <span className="mono">{e.num_echantillon}</span>
              <Typography.Text type="secondary" ellipsis className="dash-nature">{e.nature || "—"}</Typography.Text>
            </Link>
            <Space size={4}>{meta(e)}</Space>
          </Flex>
        ))}
    </Card>
  );
}

// Compteur cliquable du tableau de pilotage
function Compteur({ n, to, titre, ton }) {
  const classe = `pilotage-num ${n ? ton || "" : "zero"}`;
  return (
    <Tooltip title={titre}>
      <Link to={to} className={classe}>{n}</Link>
    </Tooltip>
  );
}

export default function Dashboard({ user }) {
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [essai, setEssai] = useState(0);   // « Réessayer » relance le chargement

  useEffect(() => {
    let actif = true;
    setErr(null);
    api.dashboard()
      .then((data) => { if (actif) setD(data); })
      .catch((e) => { if (actif) setErr(e.message); });
    return () => { actif = false; };
  }, [essai]);

  const totalStatuts = d ? STATUTS.reduce((s, k) => s + (d.parStatut?.[k] || 0), 0) : 0;
  const chiffre = (v) => (d === null ? "…" : v ?? 0);

  // Pilotage par section : chaque compteur mène à la liste filtrée
  const colonnesPilotage = [
    {
      title: "Section", dataIndex: "section", key: "section",
      render: (s) => <Link to={lienListe({ section: s })}><SectionTag code={s} /></Link>,
    },
    ...STATUTS.map((s) => ({
      title: <Tag color={STATUT_COULEUR[s]} style={{ marginInlineEnd: 0 }}>{s}</Tag>,
      key: s, align: "center",
      render: (_, sec) => (
        <Compteur n={sec.parStatut?.[s] || 0} to={lienListe({ section: sec.section, statut: s })}
                  ton={s === "À valider" ? "a-valider" : ""} />
      ),
    })),
    {
      title: "Total", key: "total", align: "center",
      render: (_, sec) => <Compteur n={sec.total} to={lienListe({ section: sec.section })} />,
    },
    {
      title: "En retard", key: "retard", align: "center",
      render: (_, sec) => (
        <>
          <Compteur n={sec.retards} ton="retard" to={lienListe({ section: sec.section, retard: "1" })}
                    titre={`Non « Rapport émis », reçus depuis plus de ${sec.delai} jours`} />
          <span className="pilotage-delai">&gt; {sec.delai} j</span>
        </>
      ),
    },
  ];

  const indicateurs = [
    ["Échantillons", d?.total],
    ["En cours de traitement", d?.enCours],
    ["À valider", d?.aValider],
    ["Terminés", d?.termines],
  ];

  return (
    <>
      <div className="page-entete">
        <Typography.Title level={4} className="page-titre">Tableau de bord</Typography.Title>
        <Typography.Text type="secondary">
          {new Date().toLocaleDateString("fr-FR",
            { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
        </Typography.Text>
      </div>

      <ErreurChargement message={err} onReessayer={() => setEssai((n) => n + 1)} />

      {/* Indicateurs */}
      <Row gutter={[16, 16]} className="bloc">
        {indicateurs.map(([titre, v]) => (
          <Col xs={12} lg={6} key={titre}>
            <Card size="small"><Statistic title={titre} value={chiffre(v)} /></Card>
          </Col>
        ))}
      </Row>

      <Card size="small" title="Pilotage par section" className="bloc">
        <Table
          size="small"
          rowKey="section"
          pagination={false}
          loading={d === null}
          columns={colonnesPilotage}
          dataSource={d ? arr(d.sections) : []}
          scroll={{ x: true }}
          className="pilotage"
        />
      </Card>

      <Row gutter={16}>
        {/* Colonne gauche : répartition + sections */}
        <Col xs={24} lg={12}>
          <Card size="small" title="Répartition par statut" className="bloc" loading={d === null}>
            {totalStatuts === 0 ? vide("Aucun échantillon.") : STATUTS.map((s) => {
              const n = d.parStatut?.[s] || 0;
              const pct = totalStatuts ? Math.round((n / totalStatuts) * 100) : 0;
              return (
                <Flex align="center" gap={12} key={s} className="repartition-ligne">
                  <span className="repartition-statut"><StatutTag statut={s} /></span>
                  <Progress percent={pct} showInfo={false} strokeColor={BARRE[s]} size="small" style={{ flex: 1, margin: 0 }} />
                  <span className="mono repartition-num">{n}</span>
                </Flex>
              );
            })}
          </Card>

          <Card size="small" title="Par section" className="bloc">
            <Row gutter={12}>
              {SECTIONS.map((s) => (
                <Col span={8} key={s.code}>
                  <Link to={`/echantillons?section=${s.code}`} className="section-carte">
                    <Statistic title={<Space size={6}><SectionTag code={s.code} />{s.nom}</Space>}
                               value={chiffre(d?.[s.key])} />
                  </Link>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>

        {/* Colonne droite : à valider, retards, récents + accès rapides */}
        <Col xs={24} lg={12}>
          <ListeEchantillons
            titre="À valider — en attente" texteVide="Aucune fiche en attente de validation."
            lignes={d === null ? null : arr(d.listeAValider)} lienTout={lienListe({ statut: "À valider" })}
            meta={(e) => <>{e.section && <SectionTag code={e.section} />}<PaiementTag statut={e.payement} /><StatutTag statut={e.statut} /></>}
          />
          <ListeEchantillons
            titre="Échantillons en retard" texteVide="Aucun retard."
            lignes={d === null ? null : arr(d.listeRetards)} lienTout={lienListe({ retard: "1" })}
            meta={(e) => (
              <>
                {e.section && <SectionTag code={e.section} />}
                <PaiementTag statut={e.payement} />
                {e.jours != null ? <Tag color="red" style={{ marginInlineEnd: 0 }}>{e.jours} j</Tag> : <StatutTag statut={e.statut} />}
              </>
            )}
          />
          <ListeEchantillons
            titre="Échantillons récents" texteVide="Aucun échantillon."
            lignes={d === null ? null : arr(d.recents)} lienTout="/echantillons"
            meta={(e) => (
              <>
                {e.sma === "Yes" && <SectionTag code="SMA" />}
                {e.scha === "Yes" && <SectionTag code="SCHA" />}
                {e.ssa === "Yes" && <SectionTag code="SSA" />}
                <PaiementTag statut={e.payement} />
                <StatutTag statut={e.statut} />
              </>
            )}
          />

          {["admin", "user"].includes(user.role) && (
            <Card size="small" title="Accès rapides" className="bloc">
              <Space wrap>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/echantillons/ajouter")}>
                  Nouvel échantillon
                </Button>
                <Button icon={<UnorderedListOutlined />} onClick={() => navigate("/echantillons")}>
                  Voir la liste
                </Button>
              </Space>
            </Card>
          )}
        </Col>
      </Row>
    </>
  );
}
