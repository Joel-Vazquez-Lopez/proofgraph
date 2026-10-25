import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PayPal AI Dispute Investigator | Hackathon 2026",
  description: "Autonomous AI-assisted PayPal dispute investigation platform with typed evidence graphs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased selection:bg-paypal-light selection:text-white">
        {children}
      </body>
    </html>
  );
}
