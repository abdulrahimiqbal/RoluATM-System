import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import MiniKitProvider from "@/components/providers/minikit-provider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "RoluATM - World ID Cash Withdrawal",
  description: "Secure cash withdrawal using World ID verification",
  keywords: ["World ID", "ATM", "Cash Withdrawal", "Cryptocurrency", "Blockchain"],
  authors: [{ name: "RoluATM Team" }],
  viewport: "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} antialiased`}
      >
        <MiniKitProvider>
          {children}
        </MiniKitProvider>
      </body>
    </html>
  );
}
