import "@fontsource-variable/sofia-sans";
import "@fontsource-variable/sofia-sans/wght-italic.css";
import "@fontsource-variable/sofia-sans-extra-condensed";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("В index.html нет элемента #root");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
