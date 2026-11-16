import { useEffect, useMemo, useState } from "react";
import { pluginsApi } from "../api/plugins";
import type { PluginPage } from "../types/plugin";

export function usePluginManifests() {
  const [pages, setPages] = useState<PluginPage[]>([]);

  useEffect(() => {
    pluginsApi
      .listPlugins(true)
      .then((plugins) =>
        setPages(
          plugins.flatMap((plugin) => plugin.frontend_manifest?.pages ?? []),
        ),
      )
      .catch(() => setPages([]));
  }, []);

  return useMemo(() => ({ pluginPages: pages }), [pages]);
}
