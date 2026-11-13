import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Kubernetes Agent",
  description: "Troubleshoot Kubernetes with AI.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 font-sans text-slate-950 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
