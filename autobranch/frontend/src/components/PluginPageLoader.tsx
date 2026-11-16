import type { ComponentType } from "react";
import { FileManager } from "../features/file/FileManager";
import { ErrorMessage } from "./ErrorMessage";
import type { PluginPage } from "../types/plugin";

const componentMap: Record<string, ComponentType> = {
  FileManager,
};

export function PluginPageLoader({ page }: { page: PluginPage }) {
  const Component = componentMap[page.component];
  if (!Component) {
    return <ErrorMessage message={`未找到插件组件: ${page.component}`} />;
  }
  return <Component />;
}
