import type { Metadata } from "next";
import { DM_Serif_Display, Inter } from "next/font/google";
import { NavHeader } from "@/components/nav-header";
import "./globals.css";

const dmSerif = DM_Serif_Display({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-dm-serif",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SecSignal — SEC Financial Intelligence",
  description:
    "Agentic RAG system for SEC financial intelligence. Analyze trends, compare companies, and detect anomalies across SEC filings.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${dmSerif.variable} ${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans">
        <NavHeader />
        {children}
      </body>
    </html>
  );
}
