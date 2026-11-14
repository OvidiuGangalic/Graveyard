import { fetchLegacyUsers } from "./api";

test("legacy endpoint still answers", async () => {
  expect(Array.isArray(await fetchLegacyUsers())).toBe(true);
});
