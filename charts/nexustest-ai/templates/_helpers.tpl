{{- define "nexustest-ai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nexustest-ai.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "nexustest-ai.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "nexustest-ai.labels" -}}
helm.sh/chart: {{ include "nexustest-ai.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- with .Values.commonLabels }}
{{- toYaml . | nindent 0 }}
{{- end -}}
{{- end -}}

{{- define "nexustest-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nexustest-ai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "nexustest-ai.componentSelectorLabels" -}}
{{ include "nexustest-ai.selectorLabels" . }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "nexustest-ai.tplValue" -}}
{{- if typeIs "string" .value -}}
{{- tpl .value .context -}}
{{- else -}}
{{- toYaml .value -}}
{{- end -}}
{{- end -}}

{{- define "nexustest-ai.configMapName" -}}
{{- if .Values.config.existingConfigMap -}}
{{- .Values.config.existingConfigMap -}}
{{- else -}}
{{- printf "%s-config" (include "nexustest-ai.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "nexustest-ai.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secret" (include "nexustest-ai.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "nexustest-ai.apiServiceName" -}}
{{- printf "%s-api" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.workerName" -}}
{{- printf "%s-celery-worker" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.beatName" -}}
{{- printf "%s-celery-beat" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.flowerName" -}}
{{- printf "%s-flower" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.nginxName" -}}
{{- printf "%s-nginx" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.redisName" -}}
{{- printf "%s-redis" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.postgresqlName" -}}
{{- printf "%s-postgresql" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.migrationsJobName" -}}
{{- printf "%s-migrations" (include "nexustest-ai.fullname" .) -}}
{{- end -}}

{{- define "nexustest-ai.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- if .Values.serviceAccount.name -}}
{{- .Values.serviceAccount.name -}}
{{- else -}}
{{- printf "%s" (include "nexustest-ai.fullname" .) -}}
{{- end -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
