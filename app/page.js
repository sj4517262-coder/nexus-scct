"use client";

import dynamic from "next/dynamic";

const SupplyChainControlTower = dynamic(
  () => import("../components/ControlTower"),
  { ssr: false },
);

export default function Home() {
  return <SupplyChainControlTower />;
}
