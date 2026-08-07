import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Elemetic",
  description: "Sistema de gestión de Elemetic",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-MX">
      <body className="min-h-dvh bg-zinc-50 text-zinc-900 antialiased">{children}</body>
    </html>
  );
}
