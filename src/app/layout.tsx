import type { Metadata } from "next";
import { Geist_Mono, Inter, Space_Grotesk } from "next/font/google";
import Script from "next/script";
import { SideRail } from "@/components/side-rail";
import { THEME_BOOT_SCRIPT, ThemeSwitcher } from "@/components/theme-switcher";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const spaceGrotesk = Space_Grotesk({ variable: "--font-space-grotesk", subsets: ["latin"], weight: ["500", "600", "700"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "GTA VI clip radar",
  description: "The GTA VI moments viewers are clipping right now on Twitch and Kick.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${spaceGrotesk.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <Script id="theme-boot" strategy="beforeInteractive">{THEME_BOOT_SCRIPT}</Script>
      </head>
      <body className="min-h-full bg-bg font-sans text-fg md:grid md:grid-cols-[76px_minmax(0,1fr)]">
        <SideRail />
        <div className="min-w-0 pb-20 md:pb-0">{children}</div>
        <div className="absolute top-3 right-4 z-20 md:fixed md:top-auto md:bottom-4">
          <ThemeSwitcher />
        </div>
      </body>
    </html>
  );
}
