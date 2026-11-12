import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Badge, Button, Empty, Popover, Typography } from "antd";
import {
  BellOutlined, CheckCircleOutlined, ClockCircleOutlined, RollbackOutlined, ToolOutlined, WarningOutlined, LineChartOutlined, SafetyCertificateOutlined, ExperimentFilled, WalletOutlined,
} from "@ant-design/icons";
import { api } from "../api/client";
import { SectionTag } from "./ui";

/**
 * Indicateur de la topbar : nombre d'éléments qui concernent l'utilisateur
 * (fiches à valider, fiches renvoyées, retards) + liste cliquable.
 * Rafraîchi à chaque changement de page et toutes les 60 s.
 */
const ICONE = {
  a_valider: <CheckCircleOutlined style={{ color: "#9A6700" }} />,
  renvoyee: <RollbackOutlined style={{ color: "#0969DA" }} />,
  retard: <ClockCircleOutlined style={{ color: "#CF222E" }} />,
  contestable: <WarningOutlined style={{ color: "#CF222E" }} />,
  etalonnage: <ToolOutlined style={{ color: "#9A6700" }} />,
  cq: <LineChartOutlined style={{ color: "#CF222E" }} />,
  habilitation: <SafetyCertificateOutlined style={{ color: "#9A6700" }} />,
  reactif: <ExperimentFilled style={{ color: "#9A6700" }} />,
  impaye: <WalletOutlined style={{ color: "#CF222E" }} />,
};
const GROUPES = [
  { type: "a_valider", titre: "À valider", cle: "aValider" },
  { type: "renvoyee", titre: "Fiches renvoyées", cle: "renvoyees" },
  { type: "retard", titre: "En retard", cle: "retards" },
  { type: "contestable", titre: "Fiches contestables (équipement)", cle: "contestables" },
  { type: "etalonnage", titre: "Étalonnages / vérifications", cle: "etalonnages" },
  { type: "cq", titre: "Contrôles qualité en alerte", cle: "cq" },
  { type: "habilitation", titre: "Habilitations à renouveler", cle: "habilitations" },
  { type: "reactif", titre: "Réactifs et milieux (péremption, stock)", cle: "reactifs" },
  { type: "impaye", titre: "Bulletins impayés", cle: "impayes" },
];

export default function Notifications() {
  const [data, setData] = useState(null);
  const [ouvert, setOuvert] = useState(false);
  const location = useLocation();

  const charger = () => api.notifications().then(setData).catch(() => setData(null));

  useEffect(() => { charger(); setOuvert(false); }, [location.pathname, location.search]);
  useEffect(() => {
    const t = setInterval(charger, 60000);
    return () => clearInterval(t);
  }, []);

  const total = data?.total || 0;
  const items = Array.isArray(data?.items) ? data.items : [];

  const contenu = (
    <div className="notif-panel">
      {total === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Rien à signaler." />}
      {GROUPES.map((g) => {
        const liste = items.filter((x) => x.type === g.type);
        const n = data?.[g.cle] || 0;
        if (!n) return null;
        return (
          <div className="notif-groupe" key={g.type}>
            <div className="notif-groupe-titre">
              {g.titre} <Badge count={n} color="#8B949E" size="small" overflowCount={999} />
            </div>
            {liste.map((x) => (
              <Link key={`${x.type}-${x.num}`} to={x.lien} className="notif-item">
                <span className="notif-ico">{ICONE[x.type]}</span>
                <span className="notif-txt">
                  <span className="notif-ligne1">
                    <span className="mono">{x.num}</span>
                    {x.section && <SectionTag code={x.section} />}
                  </span>
                  <Typography.Text type="secondary" ellipsis className="notif-ligne2">
                    {x.texte}{x.detail ? ` · ${x.detail}` : ""}
                  </Typography.Text>
                </span>
              </Link>
            ))}
            {n > liste.length && g.type === "retard" && (
              <Link to="/echantillons?retard=1" className="notif-plus">Voir les {n} retards</Link>
            )}
            {n > liste.length && g.type === "a_valider" && (
              <Link to="/echantillons?statut=À valider" className="notif-plus">Voir les {n} fiches</Link>
            )}
          </div>
        );
      })}
    </div>
  );

  return (
    <Popover
      content={contenu}
      title="Notifications"
      trigger="click"
      placement="bottomRight"
      open={ouvert}
      onOpenChange={setOuvert}
    >
      <Badge count={total} overflowCount={99} size="small" offset={[-2, 2]}>
        <Button
          type="text"
          icon={<BellOutlined />}
          className="notif-btn"
          aria-label="Notifications"
          title="Notifications"
        />
      </Badge>
    </Popover>
  );
}
