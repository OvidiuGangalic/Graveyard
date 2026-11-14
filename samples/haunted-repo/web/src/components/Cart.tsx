import { useMemo, useState } from "react";
import { Banner } from "./Banner";
import { formatDate } from "../utils/dates";
import { formatCurrency } from "../utils/format";

type CartProps = { prices: number[] };

export function Cart({ prices }: CartProps) {
  const [open, setOpen] = useState(true);
  const total = prices.reduce((sum, price) => sum + price, 0);
  return (
    <section>
      <Banner text={`Updated ${formatDate(new Date())}`} />
      <button onClick={() => setOpen(!open)}>Toggle</button>
      {open ? <p>{formatCurrency(total)}</p> : null}
    </section>
  );
}
