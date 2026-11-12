import { useState } from "react";
import { Alert, Button, Card, Form, Input, Typography } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { api } from "../api/client";

export default function Login({ onLogin, expiree = false }) {
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const submit = async ({ username, password }) => {
    setErr(null);
    setEnvoi(true);
    try { await onLogin(await api.login(username, password)); }
    catch (e2) { setErr(e2.message); setEnvoi(false); }
  };

  return (
    <div className="login-page">
      <Card className="login-card" variant="borderless">
        <Typography.Title level={4} className="login-titre">Labo Manager</Typography.Title>
        <Typography.Text type="secondary">LRARVY — ONSSA</Typography.Text>
        {expiree && !err && (
          <Alert type="warning" showIcon style={{ margin: "16px 0 0" }}
                 title="Session expirée. Reconnectez-vous : vous reviendrez à la page où vous étiez." />
        )}
        {import.meta.env.VITE_ENVIRONNEMENT === "demo" && (
          <Alert type="info" title="Démonstration — données fictives" showIcon style={{ margin: "16px 0 0" }} />
        )}
        {err && <Alert type="error" title={err} showIcon style={{ margin: "16px 0 0" }} />}
        <Form name="login" layout="vertical" onFinish={submit} requiredMark={false}
              style={{ marginTop: 16 }}>
          <Form.Item label="Utilisateur" name="username"
                     rules={[{ required: true, message: "Saisissez votre nom d'utilisateur" }]}>
            <Input prefix={<UserOutlined />} autoFocus autoComplete="username" />
          </Form.Item>
          <Form.Item label="Mot de passe" name="password"
                     rules={[{ required: true, message: "Saisissez votre mot de passe" }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={envoi}>Se connecter</Button>
        </Form>
      </Card>
    </div>
  );
}
