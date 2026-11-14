import { Badge } from "@/components/Badge";
import Wrapper from "@/components/Panel";
import "@/lib/cart";
import * as utils from "@/utils";
import { fmt as fmtMoney } from "@/utils/money";
import { fmt as fmtDate } from "@/utils/date";
import type { Item } from "@/lib/types";
import { loadItems } from "@/lib/api";

const slug = require("../../lib/slug.js").slug;

export default function Home() {
  const first: Item = { id: 1, name: "Big Box", price: 5 };
  return (
    <Wrapper>
      <Badge label={slug(first.name)} />
      <p>{fmtMoney(first.price)} {fmtDate(new Date(0))} {utils.pad("7", 3)}</p>
      <button onClick={() => loadItems()}>Reload</button>
    </Wrapper>
  );
}
