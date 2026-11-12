import { Alert, Button, Empty } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

/**
 * États communs des pages (tâche 31).
 * - ErreurChargement : les données n'ont pas pu être chargées ; « Réessayer » relance le chargement.
 *   (Pour l'échec d'une action — enregistrement, validation — garder une Alert simple : recharger
 *   ferait perdre la saisie.)
 * - Vide : liste vide, avec une action utile quand l'utilisateur peut en faire une.
 */
export function ErreurChargement({ message, onReessayer, style }) {
  if (!message) return null;
  return (
    <Alert type="error" showIcon title={message} style={{ marginBottom: 12, ...style }}
           action={onReessayer && (
             <Button size="small" icon={<ReloadOutlined />} onClick={onReessayer}>Réessayer</Button>
           )} />
  );
}

export function Vide({ texte, action }) {
  return (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={texte}>
      {action}
    </Empty>
  );
}
