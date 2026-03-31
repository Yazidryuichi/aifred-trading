import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { TradingModeBanner } from "@/components/TradingModeBanner";
import { Web3Provider } from "@/components/providers/Web3Provider";

export const metadata: Metadata = {
  title: "AIFred — Multi-Agent Trading Intelligence",
  description:
    "7-agent AI-powered trading system with deep learning, NLP sentiment analysis, and adaptive risk management.",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#06060a] text-white antialiased">
        <Providers>
          <TradingModeBanner />
          <Web3Provider>{children}</Web3Provider>
        </Providers>
      </body>
    </html>
  );
}
