import { NextResponse } from "next/server";

/** Liveness probe for the container healthcheck / load balancer. */
export function GET() {
  return NextResponse.json({ status: "ok" });
}
