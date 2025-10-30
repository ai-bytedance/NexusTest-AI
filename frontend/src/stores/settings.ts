import { create } from "zustand";
import { persist } from "zustand/middleware";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import "dayjs/locale/en";
import i18n, { DEFAULT_LANGUAGE, type SupportedLanguage } from "@/i18n";

interface SettingsState {
  language: SupportedLanguage;
  setLanguage: (language: SupportedLanguage) => void;
}

const STORAGE_KEY = "app.language";

function applyLanguage(language: SupportedLanguage) {
  void i18n.changeLanguage(language);
  dayjs.locale(language === "zh" ? "zh-cn" : "en");
  if (typeof document !== "undefined") {
    document.documentElement.lang = language;
    document.body.dir = "ltr";
  }
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      language: DEFAULT_LANGUAGE,
      setLanguage: (language) => {
        if (get().language === language) {
          return;
        }
        applyLanguage(language);
        set({ language });
      },
    }),
    {
      name: STORAGE_KEY,
      partialize: (state) => ({ language: state.language }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          applyLanguage(state.language);
        }
      },
    }
  )
);

applyLanguage(DEFAULT_LANGUAGE);

export const selectLanguage = (state: SettingsState) => state.language;
