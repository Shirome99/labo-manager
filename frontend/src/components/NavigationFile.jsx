import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Space, Typography } from "antd";
import { LeftOutlined, RightOutlined } from "@ant-design/icons";
import { api } from "../api/client";

/**
 * « Précédent / Suivant » dans la file de travail (Mon travail), sans revenir à la liste.
 * La file est celle de l'utilisateur, limitée à la section de la page ; elle est relue
 * à chaque changement d'échantillon (un échantillon soumis ou validé en sort).
 * page : "traitement" | "resultats"
 */
export default function NavigationFile({ section, num, page }) {
  const navigate = useNavigate();
  const [file, setFile] = useState([]);

  useEffect(() => {
    let actif = true;
    api.travail()
      .then((d) => {
        if (!actif) return;
        const items = Array.isArray(d?.items) ? d.items : [];
        setFile(items.filter((x) => x.section === section && x.lien.startsWith("/traitement/")).map((x) => x.num));
      })
      .catch(() => actif && setFile([]));
    return () => { actif = false; };
  }, [section, num]);

  if (file.length === 0) return null;
  const idx = file.indexOf(num);
  const aller = (n) => navigate(`/${page}/${section}?num=${encodeURIComponent(n)}`);
  const precedent = idx > 0 ? file[idx - 1] : null;
  const suivant = idx < 0 ? file[0] : (idx < file.length - 1 ? file[idx + 1] : null);

  return (
    <Space size={8} className="navigation-file">
      <Typography.Text type="secondary">
        File de travail : {idx >= 0 ? `${idx + 1} / ${file.length}` : `${file.length} à traiter`}
      </Typography.Text>
      <Button size="small" icon={<LeftOutlined />} disabled={!precedent} onClick={() => aller(precedent)}>
        Précédent
      </Button>
      <Button size="small" disabled={!suivant} onClick={() => aller(suivant)}>
        Suivant <RightOutlined />
      </Button>
    </Space>
  );
}
