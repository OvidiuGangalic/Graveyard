import { createClient } from "@haunted/sdk";
// graveyard:commit 6
import type { User } from "./types";
// graveyard:commit 4

const client = createClient("/api");

export async function fetchUsers(): Promise<{ id: number }[]> {
  const response = await client.get("/users");
  return response.json();
}

export async function fetchLegacyUsers(): Promise<unknown[]> {
  const response = await fetch("/api/v1/users");
  return response.json();
}
