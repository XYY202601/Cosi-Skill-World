import { NextResponse } from "next/server";

import { getDeployEnv, getPlatformApiBase } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";

export async function GET() {
  const deployEnv = getDeployEnv();
  const hermesBase = getPlatformApiBase();

  return NextResponse.json({
    status: "ok",
    service: "web",
    deploy_env: deployEnv,
    hermes_api_base: hermesBase,
    fallback_disabled: deployEnv !== "development",
  });
}
