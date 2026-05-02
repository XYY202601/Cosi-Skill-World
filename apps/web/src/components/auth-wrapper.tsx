"use client";

import { AuthProvider } from "@/lib/auth-context";

export function AuthWrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
