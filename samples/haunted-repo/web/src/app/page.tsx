import { lazy, Suspense } from "react";
import { Cart } from "../components/Cart";
import { fetchUsers } from "../lib/api";

const LazyPromo = lazy(() => import("../components/OldBanner"));

export default async function Page() {
  const users = await fetchUsers();
  return (
    <main>
      <Suspense fallback={null}>
        <LazyPromo />
      </Suspense>
      <p>{users.length} customers</p>
      <Cart prices={[4, 8, 15]} />
    </main>
  );
}
