import type { Metadata } from "next";
import { Playfair_Display, Lato } from "next/font/google";
import Script from "next/script";

import { ThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from "@/contexts/AuthProvider";
import "./globals.css";

// Configure the Serif font for Legal Headers
const playfair = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
});

// Configure the Sans-Serif font for standard text
const lato = Lato({
  variable: "--font-lato",
  subsets: ["latin"],
  weight: ["400", "700"], // Lato requires specific weights to be declared
});

// Update the browser tab title and SEO description
export const metadata: Metadata = {
  title: "LankaLawBot | AI Legal Assistant",
  description:
    "A Generative AI Agentic Framework for Personalized Legal Drafting and Case Intelligence within the Sri Lankan Jurisdiction.",
};

const themeInitializer = `
(function () {
  var theme = "dark";
  try {
    var stored = localStorage.getItem("lankalawbot-theme");
    var parsed = stored ? JSON.parse(stored) : null;
    var savedTheme = parsed && parsed.state && parsed.state.theme;
    if (savedTheme === "light" || savedTheme === "dark") theme = savedTheme;
  } catch (_) {}
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${playfair.variable} ${lato.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-app-canvas font-sans text-app-primary">
        <Script id="theme-initializer" strategy="beforeInteractive">
          {themeInitializer}
        </Script>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
