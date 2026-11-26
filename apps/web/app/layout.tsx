import type { Metadata } from "next";
import type { ReactNode } from "react";
import { themeInitScript } from "@sendora/ui-kit";
import "@sendora/ui-kit/styles.css";
import "./globals.css";
import { Providers } from "@/components/Providers";

export const metadata: Metadata = { title: "Lorefern", description: "A company knowledge base with cited answers and a visibility tag on every document." };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-accent="teal" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
