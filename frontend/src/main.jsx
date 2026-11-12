import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, App as AntApp } from "antd";
import frFR from "antd/locale/fr_FR";
import dayjs from "dayjs";
import "dayjs/locale/fr";
import App from "./App";
import "./style.css";

dayjs.locale("fr");

// Thème antd : vert du labo, rayons sobres, police Instrument Sans
const theme = {
  token: {
    colorPrimary: "#00875A",
    colorLink: "#00875A",
    borderRadius: 6,
    fontFamily: "'Instrument Sans', -apple-system, 'Segoe UI', sans-serif",
    fontSize: 14,
  },
  components: {
    Layout: {
      headerBg: "#0D1117",
      headerHeight: 52,
      headerPadding: "0 20px",
      siderBg: "#FFFFFF",
      lightSiderBg: "#FFFFFF",
      bodyBg: "#F6F8FA",
    },
    Menu: {
      itemHeight: 34,
      itemMarginBlock: 2,
      itemSelectedBg: "#E3FCEF",
      itemSelectedColor: "#006644",
      itemActiveBg: "#F0F2F5",
      itemHoverBg: "#F6F8FA",
      subMenuItemBg: "#FFFFFF",
      groupTitleFontSize: 11,
    },
    Card: { headerFontSize: 14 },
  },
};

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ConfigProvider locale={frFR} theme={theme}>
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
