export function retry<T>(fn: () => Promise<T>): Promise<T> {
  return fn().catch(() => fn());
}
