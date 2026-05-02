import type { Metadata } from "next";

import { SiteHeader } from "@/components/site-header";
import { AuthWrapper } from "@/components/auth-wrapper";

import "./globals.css";

export const metadata: Metadata = {
  title: "MR Visit JP Training Gym",
  description: "Alpha training flow for Japanese MR visits.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="page-bg" />
        <div className="site-shell">
          <div className="site-frame">
            <AuthWrapper>
              <SiteHeader />
              <main className="site-main">{children}</main>
            </AuthWrapper>
          </div>
        </div>
      </body>
    </html>
  );
}
