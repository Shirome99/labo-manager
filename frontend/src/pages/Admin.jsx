import { useEffect, useState } from "react";
import { Alert, App, Button, Card, Col, Form, Input, Modal, Row, Select, Space, Table, Tag, Typography } from "antd";
import { UserAddOutlined } from "@ant-design/icons";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";
import { REGLES_MOT_DE_PASSE, ROLES, SectionTag } from "../components/ui";

const OPTIONS_ROLES = ROLES.map((r) => ({ value: r, label: <SectionTag code={r} /> }));

export default function Admin({ user }) {
  const { modal, message } = App.useApp();
  const [form] = Form.useForm();
  const [users, setUsers] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const charger = () => {
    setChargement(true);
    return api.users()
      .then((d) => setUsers(Array.isArray(d) ? d : []))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => { charger(); }, []);

  const creer = async (valeurs) => {
    setErr(null);
    setEnvoi(true);
    try {
      await api.creerUser({ ...valeurs, email: valeurs.email || "" });
      form.resetFields();
      message.success("Compte créé.");
      charger();
    } catch (e2) { setErr(e2.message); }
    finally { setEnvoi(false); }
  };

  const changerRole = async (id, role) => {
    try { await api.changerRole(id, role); message.success("Rôle modifié."); charger(); }
    catch (e) { message.error(e.message); }
  };

  // Réinitialisation du mot de passe par l'admin (déverrouille aussi le compte)
  const [reinit, setReinit] = useState(null);
  const [formReinit] = Form.useForm();
  const reinitialiser = async ({ nouveau }) => {
    try {
      await api.reinitialiserMotDePasse(reinit.id, nouveau);
      message.success(`Mot de passe de ${reinit.username} réinitialisé.`);
      setReinit(null);
      formReinit.resetFields();
      charger();
    } catch (e) { message.error(e.message); }
  };
  const deverrouiller = async (u) => {
    try { await api.deverrouillerUser(u.id); message.success(`Compte ${u.username} déverrouillé.`); charger(); }
    catch (e) { message.error(e.message); }
  };
  const estVerrouille = (u) => u.verrouille_jusqu && new Date(u.verrouille_jusqu) > new Date();

  const supprimer = (u) => modal.confirm({
    title: `Supprimer le compte ${u.username} ?`,
    okText: "Supprimer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { await api.supprimerUser(u.id); message.success("Compte supprimé."); charger(); }
      catch (e) { message.error(e.message); }
    },
  });

  const colonnes = [
    {
      title: "Utilisateur", dataIndex: "username", key: "username",
      sorter: (a, b) => String(a.username).localeCompare(String(b.username), "fr"),
      render: (v) => <span className="mono">{v}</span>,
    },
    { title: "Email", dataIndex: "email", key: "email", render: (v) => v || "—" },
    {
      title: "Rôle", dataIndex: "role", key: "role", width: 140,
      filters: ROLES.map((r) => ({ text: r.toUpperCase(), value: r })),
      onFilter: (v, u) => u.role === v,
      render: (v, u) => (
        <Select size="small" value={v} options={OPTIONS_ROLES} style={{ width: 140 }}
                onChange={(r) => changerRole(u.id, r)} />
      ),
    },
    {
      title: "État", key: "etat", width: 190,
      render: (_, u) => (estVerrouille(u)
        ? <Tag color="red">Verrouillé jusqu'à {new Date(u.verrouille_jusqu).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</Tag>
        : <Tag color="green">Actif</Tag>),
    },
    {
      title: "", key: "actions", align: "right", width: 330,
      render: (_, u) => (
        <Space size={12}>
          {estVerrouille(u) && (
            <Button type="link" size="small" className="btn-lien" onClick={() => deverrouiller(u)}>Déverrouiller</Button>
          )}
          <Button type="link" size="small" className="btn-lien" onClick={() => setReinit(u)}>
            Réinitialiser le mot de passe
          </Button>
          {u.id !== user.id && (
            <Button type="link" danger size="small" className="btn-lien" onClick={() => supprimer(u)}>
              Supprimer
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <div className="page-entete">
        <Typography.Title level={4} className="page-titre">Comptes utilisateurs</Typography.Title>
      </div>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />

      <Card size="small" title="Créer un compte" className="bloc">
        <Form form={form} layout="vertical" onFinish={creer} initialValues={{ role: "user" }} className="form-dense">
          <Row gutter={16}>
            <Col xs={24} sm={12} lg={6}>
              <Form.Item label="Utilisateur" name="username" rules={[
                { required: true, message: "Saisissez un nom d'utilisateur" },
                { min: 3, message: "3 caractères minimum" },
              ]}>
                <Input autoComplete="off" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Form.Item label="Email (optionnel)" name="email"
                         rules={[{ type: "email", message: "Adresse e-mail invalide" }]}>
                <Input placeholder="auto si vide" autoComplete="off" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Form.Item label="Mot de passe" name="password" rules={REGLES_MOT_DE_PASSE}
                         tooltip="Au moins 10 caractères, dont des lettres et des chiffres">
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Form.Item label="Rôle" name="role"><Select options={OPTIONS_ROLES} /></Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" icon={<UserAddOutlined />} loading={envoi}>Créer</Button>
        </Form>
      </Card>

      <Modal title={`Réinitialiser le mot de passe de ${reinit?.username || ""}`} open={Boolean(reinit)}
             okText="Réinitialiser" cancelText="Annuler" onOk={() => formReinit.submit()}
             onCancel={() => { setReinit(null); formReinit.resetFields(); }} destroyOnHidden>
        <Typography.Paragraph type="secondary">
          Le compte est aussi déverrouillé. Communiquez le nouveau mot de passe à l'utilisateur,
          qui pourra le changer depuis le bouton « Mot de passe » de l'en-tête.
        </Typography.Paragraph>
        <Form form={formReinit} layout="vertical" onFinish={reinitialiser}>
          <Form.Item label="Nouveau mot de passe" name="nouveau" rules={REGLES_MOT_DE_PASSE}>
            <Input.Password autoComplete="new-password" autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      <Table size="small" rowKey="id" columns={colonnes} dataSource={users} loading={chargement}
             pagination={users.length > 50 ? { pageSize: 50 } : false} />
    </>
  );
}
