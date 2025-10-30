import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import resourcesToBackend from "i18next-resources-to-backend";

export const SUPPORTED_LANGUAGES = ["zh", "en"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export const DEFAULT_LANGUAGE: SupportedLanguage = "zh";

export const NAMESPACES = [
  "common",
  "app",
  "login",
  "navigation",
  "dashboard",
  "projects",
  "apis",
  "cases",
  "suites",
  "reports",
  "editor",
  "errors",
  "states",
] as const;

const savedLanguage =
  typeof window !== "undefined" ? (localStorage.getItem("app.language") as SupportedLanguage | null) : null;

void i18n
  .use(initReactI18next)
  .use(
    resourcesToBackend((language: string, namespace: string) =>
      import(`./locales/${language}/${namespace}.json`).then((module) => module.default)
    )
  )
  .init({
    lng: savedLanguage ?? DEFAULT_LANGUAGE,
    fallbackLng: "en",
    ns: NAMESPACES,
    defaultNS: "common",
    load: "languageOnly",
    supportedLngs: SUPPORTED_LANGUAGES,
    interpolation: {
      escapeValue: false,
    },
    returnNull: false,
  });

export default i18n;
