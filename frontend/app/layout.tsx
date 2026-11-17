import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/lib/auth-context";
import { LanguageProvider } from "@/lib/i18n/context";
import { ThemeProvider } from "@/lib/theme-context";
import { ToastProvider } from "@/components/ui/Toast";
import "./globals.css";

// Runs before paint (blocking inline script in <head>) so a viewer who
// previously chose light mode never sees a flash of the dark default on
// reload. Dark stays the default for everyone else - this only ever
// adds the attribute, never removes it, matching lib/theme-context.tsx.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("cynvexa-theme");if(t==="light"){document.documentElement.setAttribute("data-theme","light");}}catch(e){}})();`;

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "CYNVEXA Fuel Retail ERP",
  description: "Operational and financial reconciliation for fuel retail stations.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-ink">
        <ThemeProvider>
          <LanguageProvider>
            <AuthProvider>
              <ToastProvider>{children}</ToastProvider>
            </AuthProvider>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
