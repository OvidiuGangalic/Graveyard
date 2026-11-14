export function fmt(value: Date) {
  return value.toISOString().slice(0, 10);
}
