import { useCallback } from "react";
import type { SupportedLanguage } from "@/i18n";
import { selectLanguage, useSettingsStore } from "@/stores";

export function useLanguage() {
  const language = useSettingsStore(selectLanguage);
  const setLanguage = useSettingsStore((state) => state.setLanguage);

  const changeLanguage = useCallback(
    (nextLanguage: SupportedLanguage) => {
      setLanguage(nextLanguage);
    },
    [setLanguage]
  );

  return {
    language,
    changeLanguage,
  };
}
