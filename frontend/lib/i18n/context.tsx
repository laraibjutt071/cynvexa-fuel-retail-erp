"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { translations, type Language, type TranslationKey } from "./translations";

const STORAGE_KEY = "cynvexa_lang";

interface LanguageContextValue {
  language: Language;
  setLanguage: (lang: Language) => void;
  /** Looks up a translation key; falls back to the key itself if missing
   * (visible-but-harmless, never a blank screen) so a typo in a key never
   * breaks the page. */
  t: (key: TranslationKey) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

/**
 * No backend field exists yet for a user's language preference (see
 * docs/UX_UPGRADE_PLAN.md Stage 3) - this is a documented client-only
 * preference until a future phase adds server-side persistence. Switching
 * language never touches form state or the session; it is purely a read
 * of this context by already-rendered components.
 */
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "en" || stored === "ur") {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setLanguageState(stored);
      }
    } catch {
      // Storage unavailable (private browsing, blocked cookies) - stay on
      // the English default rather than failing the whole page.
    }
  }, []);

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang);
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // Best-effort only - the in-memory state above still updates.
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey) => translations[key]?.[language] ?? String(key),
    [language]
  );

  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within a LanguageProvider");
  return ctx;
}
