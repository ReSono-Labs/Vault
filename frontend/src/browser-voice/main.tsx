import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserVoiceApp } from "@/browser-voice/BrowserVoiceApp";
import "@/browser-voice/browser-voice.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode><BrowserVoiceApp /></React.StrictMode>,
);
