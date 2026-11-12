import { useState } from "react";
import { App, Form, Input, Modal, Typography } from "antd";
import { api } from "../api/client";
import { REGLES_MOT_DE_PASSE } from "./ui";

/** Modale : l'utilisateur connecté change son propre mot de passe. */
export default function MotDePasse({ ouvert, onFermer }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [envoi, setEnvoi] = useState(false);

  const fermer = () => { form.resetFields(); onFermer(); };

  const valider = async ({ actuel, nouveau }) => {
    setEnvoi(true);
    try {
      await api.changerMotDePasse(actuel, nouveau);
      message.success("Mot de passe modifié.");
      fermer();
    } catch (e) {
      message.error(e.message);
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <Modal title="Changer mon mot de passe" open={ouvert} okText="Enregistrer" cancelText="Annuler"
           confirmLoading={envoi} onOk={() => form.submit()} onCancel={fermer} destroyOnHidden>
      <Typography.Paragraph type="secondary">
        Au moins 10 caractères, dont des lettres et des chiffres.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" onFinish={valider} className="form-dense">
        <Form.Item label="Mot de passe actuel" name="actuel"
                   rules={[{ required: true, message: "Saisissez votre mot de passe actuel" }]}>
          <Input.Password autoComplete="current-password" autoFocus />
        </Form.Item>
        <Form.Item label="Nouveau mot de passe" name="nouveau" rules={REGLES_MOT_DE_PASSE} hasFeedback>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          label="Confirmation" name="confirmation" dependencies={["nouveau"]} hasFeedback
          rules={[
            { required: true, message: "Confirmez le nouveau mot de passe" },
            ({ getFieldValue }) => ({
              validator: (_, v) => (!v || v === getFieldValue("nouveau")
                ? Promise.resolve() : Promise.reject(new Error("Les deux saisies sont différentes"))),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
