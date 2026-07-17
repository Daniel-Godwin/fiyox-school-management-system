import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fiyox — School Management",
  description:
    "Multi-tenant school management for Nigerian secondary schools: results, fees, attendance, and parent communication.",
};

// Without this, every phone renders the desktop layout shrunk to unreadable.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // allow pinch-zoom (accessibility) but start at natural size
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Fonts load at runtime with system fallbacks — the app never blocks on them. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      {/* suppressHydrationWarning: browser extensions (password managers etc.)
          inject attributes into the DOM before React hydrates; this silences
          that attribute-level noise only — real content mismatches still warn. */}
      <body className="antialiased" suppressHydrationWarning>{children}</body>
    </html>
  );
}
