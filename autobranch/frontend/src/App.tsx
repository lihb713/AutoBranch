import { Navigate, Route, Routes } from "react-router-dom";
import { GlobalNav } from "./components/GlobalNav";
import { PluginEditorPage } from "./features/plugins/PluginEditorPage";
import { PluginListPage } from "./features/plugins/PluginListPage";
import { RunListPage } from "./features/runs/RunListPage";
import { TreeEditorPage } from "./features/tree-editor/TreeEditorPage";
import { TreeListPage } from "./features/tree-editor/TreeListPage";
import { RunReportPage } from "./features/runs/RunReportPage";

export default function App() {
  return (
    <div className="app">
      <GlobalNav />
      <Routes>
        <Route path="/" element={<TreeListPage />} />
        <Route path="/editor/:id?" element={<TreeEditorPage />} />
        <Route path="/runs" element={<RunListPage />} />
        <Route path="/runs/:runId" element={<RunReportPage />} />
        <Route path="/plugins" element={<PluginListPage />} />
        <Route path="/plugins/new" element={<PluginEditorPage />} />
        <Route path="/plugins/edit/:name" element={<PluginEditorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}