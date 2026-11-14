export function createClient(baseUrl: string) {
  return { baseUrl, get: (path: string) => fetch(baseUrl + path) };
}

export function createLegacyClient(baseUrl: string, apiKey: string) {
  return { baseUrl, apiKey };
}
