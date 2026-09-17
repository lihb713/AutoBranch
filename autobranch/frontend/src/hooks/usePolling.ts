import { useEffect, useRef, useState } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  shouldStop: (data: T) => boolean,
  intervalMs = 1000,
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const fetcherRef = useRef(fetcher);
  const shouldStopRef = useRef(shouldStop);

  useEffect(() => {
    fetcherRef.current = fetcher;
    shouldStopRef.current = shouldStop;
  }, [fetcher, shouldStop]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        const next = await fetcherRef.current();
        if (cancelled) return;
        setData(next);
        if (shouldStopRef.current(next)) {
          return;
        }
        timer = setTimeout(tick, intervalMs);
      } catch (err) {
        if (!cancelled) {
          setError(err as Error);
        }
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [intervalMs]);

  return { data, error };
}