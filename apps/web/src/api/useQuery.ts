import { useEffect, useState } from "react";

// Minimal keyed query cache. Positions are revisited constantly while navigating a game,
// so results are cached per key and concurrent requests for the same key are shared.

type Entry = { promise: Promise<unknown>; value?: unknown; error?: unknown; settled: boolean };
const cache = new Map<string, Entry>();
const MAX_ENTRIES = 500;

function load<T>(key: string, fetcher: () => Promise<T>): Entry {
  let entry = cache.get(key);
  if (entry && !(entry.settled && entry.error)) return entry; // errors are retried on next use
  const e: Entry = { settled: false, promise: Promise.resolve() };
  e.promise = fetcher().then(
    (v) => {
      e.value = v;
      e.settled = true;
    },
    (err) => {
      e.error = err;
      e.settled = true;
    },
  );
  cache.set(key, e);
  if (cache.size > MAX_ENTRIES) cache.delete(cache.keys().next().value!);
  entry = e;
  return entry;
}

export interface QueryState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
}

/** `key === null` disables the query. */
export function useQuery<T>(key: string | null, fetcher: () => Promise<T>): QueryState<T> {
  const read = (): QueryState<T> => {
    if (key === null) return { data: undefined, error: undefined, loading: false };
    const e = cache.get(key);
    if (!e || !e.settled) return { data: undefined, error: undefined, loading: true };
    return { data: e.value as T | undefined, error: e.error, loading: false };
  };
  const [state, setState] = useState<QueryState<T>>(read);

  useEffect(() => {
    if (key === null) {
      setState({ data: undefined, error: undefined, loading: false });
      return;
    }
    let live = true;
    const entry = load(key, fetcher);
    setState(read());
    entry.promise.then(() => live && setState(read()));
    return () => {
      live = false;
    };
    // fetcher is intentionally not a dependency: the key fully identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}

export function peekQuery<T>(key: string): T | undefined {
  const e = cache.get(key);
  return e?.settled ? (e.value as T | undefined) : undefined;
}
