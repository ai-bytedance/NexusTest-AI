import { Segmented } from "antd";
import { useTranslation } from "react-i18next";
import type { SupportedLanguage } from "@/i18n";
import { useLanguage } from "@/hooks/useLanguage";

const LANGUAGE_OPTIONS: SupportedLanguage[] = ["zh", "en"];

export function LanguageSwitcher() {
  const { t } = useTranslation("app");
  const { language, changeLanguage } = useLanguage();

  return (
    <Segmented
      options={LANGUAGE_OPTIONS.map((value) => ({
        label: t(`language.${value}`),
        value,
      }))}
      value={language}
      onChange={(value) => changeLanguage(value as SupportedLanguage)}
      aria-label={t("languageLabel")}
      size="small"
    />
  );
}
