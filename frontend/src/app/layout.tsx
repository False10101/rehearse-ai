import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth/auth-provider";
import { AuthRouteGuard } from "@/components/auth/auth-route-guard";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://rehearse-ai.pyrx.net"),
  title: "Rehearse AI",
  description: "AI-powered presentation coaching for university students.",
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "Rehearse AI",
    url: "/",
    title: "Rehearse AI — Your presentation coach",
    description: "Clearer slides. Stronger words. Better delivery. Prepare your slides and script, then practise with live and recorded feedback.",
    images: [{
      url: "/social/rehearse-ai-v1.png",
      width: 1200,
      height: 630,
      type: "image/png",
      alt: "Rehearse AI: Clearer slides. Stronger words. Better delivery.",
    }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Rehearse AI — Your presentation coach",
    description: "Prepare your slides and script, then practise with live and recorded feedback.",
    images: ["/social/rehearse-ai-v1.png"],
  },
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
