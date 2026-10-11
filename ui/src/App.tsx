import { useEffect } from "react";
import { applyTheme, loadThemePreference } from "./design/useTheme";
import { AppShell } from "./app-shell/AppShell";

// Questor 前端入口：挂主题（light/dark），渲染第一屏工作台骨架。
export default function App() {
  useEffect(() => {
    applyTheme(loadThemePreference());
  }, []);
  return <AppShell />;
}
