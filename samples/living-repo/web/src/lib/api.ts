import { retry } from "./retry";

export async function loadItems(limit?: number) {
  const url = "/api/items?limit=" + (limit ?? 20);
  return retry(() => fetch(url).then((r) => r.json()));
}
