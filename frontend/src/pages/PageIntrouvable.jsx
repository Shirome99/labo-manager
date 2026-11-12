import { Link, useLocation } from "react-router-dom";
import { Button, Card, Empty, Space, Typography } from "antd";

/** Page 404 : adresse inconnue dans l'application (tâche 31). */
export default function PageIntrouvable() {
  const { pathname } = useLocation();
  return (
    <Card size="small" className="bloc">
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={
        <Space orientation="vertical" size={4}>
          <Typography.Text strong>Page introuvable</Typography.Text>
          <Typography.Text type="secondary">
            L'adresse <span className="mono">{pathname}</span> ne correspond à aucune page de l'application.
          </Typography.Text>
        </Space>
      }>
        <Space>
          <Link to="/"><Button type="primary">Retour à l'accueil</Button></Link>
          <Link to="/echantillons"><Button>Liste des échantillons</Button></Link>
        </Space>
      </Empty>
    </Card>
  );
}
