import type { Metadata } from "next";
import { Playfair_Display, Lato } from "next/font/google";
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
  description: "A Generative AI Agentic Framework for Personalized Legal Drafting and Case Intelligence within the Sri Lankan Jurisdiction.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${playfair.variable} ${lato.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans text-slate-800 bg-[#F5F6F8]">
        {children}
      </body>
    </html>
  );
}