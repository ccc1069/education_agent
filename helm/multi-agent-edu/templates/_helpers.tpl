{{/*
Common labels
*/}}
{{- define "multi-agent-edu.labels" -}}
app.kubernetes.io/name: multi-agent-edu
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: api
app.kubernetes.io/part-of: multi-agent-edu
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "multi-agent-edu.selectorLabels" -}}
app.kubernetes.io/name: multi-agent-edu
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: api
{{- end -}}

{{/*
Service account name
*/}}
{{- define "multi-agent-edu.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (printf "%s" .Release.Name) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image reference
*/}}
{{- define "multi-agent-edu.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end -}}

{{/*
ConfigMap name
*/}}
{{- define "multi-agent-edu.configMapName" -}}
{{ .Release.Name }}-config
{{- end -}}

{{/*
Secret name
*/}}
{{- define "multi-agent-edu.secretName" -}}
{{ .Release.Name }}-secret
{{- end -}}
