import { CSSProperties, useMemo } from "react";
import { Select } from "antd";
import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";

interface ProjectSelectorProps {
  value?: string | null;
  onChange?: (projectId: string | null) => void;
  style?: CSSProperties;
  allowClear?: boolean;
}

export function ProjectSelector({ value, onChange, style, allowClear = false }: ProjectSelectorProps) {
  const { t } = useTranslation();
  const { projects, selectedProjectId, setSelectedProject, loading, refresh } = useProjects({
    autoLoad: false,
  });

  const currentValue = value ?? selectedProjectId ?? undefined;

  const options = useMemo(
    () =>
      projects.map((project) => ({
        label: `${project.name} (${project.key})`,
        value: project.id,
      })),
    [projects]
  );

  const handleChange = (projectId: string | null) => {
    const nextValue = projectId ?? null;
    setSelectedProject(nextValue);
    onChange?.(nextValue);
  };

  return (
    <Select
      showSearch
      allowClear={allowClear}
      value={currentValue}
      placeholder={t("app.projectSelector")}
      options={options}
      onChange={(newValue) => handleChange(newValue ?? null)}
      loading={loading}
      style={{ minWidth: 220, ...style }}
      filterOption={(input, option) =>
        (option?.label as string).toLowerCase().includes(input.toLowerCase())
      }
      onDropdownVisibleChange={(open) => {
        if (open) {
          void refresh();
        }
      }}
    />
  );
}

export default ProjectSelector;
