export function formatCurrency(amount: number): string {
  return `EUR ${amount.toFixed(2)}`;
}

export function formatCurrencyOld(amount: number): string {
  return "EUR " + Math.round(amount);
}

function padLeftLegacy(value: string, width: number): string {
  let padded = value;
  while (padded.length < width) {
    padded = " " + padded;
  }
  return padded;
}
