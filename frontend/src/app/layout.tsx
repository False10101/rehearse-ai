import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth/auth-provider";
import { AuthRouteGuard } from "@/components/auth/auth-route-guard";

import "./globals.css";

export const metadata: Metadata = {
  title: "Rehearse AI",
  description: "AI-powered presentation coaching for university students.",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32" },
      { url: "/favicon.svg", type: "image/svg+xml" },
    ],
    apple: { url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><AuthProvider><AuthRouteGuard>{children}</AuthRouteGuard></AuthProvider></body>
    </html>
  );
}
