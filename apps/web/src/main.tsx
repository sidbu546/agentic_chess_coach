import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@lichess-org/chessground/assets/chessground.base.css";
import "./styles/board.css";
import "./styles/app.css";

import { createTheme, MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// En Croissant uses Mantine's dark scheme with the default blue primary.
const theme = createTheme({
  primaryColor: "blue",
  defaultRadius: "sm",
  fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <Notifications position="bottom-right" />
      <App />
    </MantineProvider>
  </StrictMode>,
);
