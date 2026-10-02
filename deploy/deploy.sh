#!/usr/bin/env bash
# Deploy dashi/app to the team namespace at http://<team host>/app (deploy-app-no-registry skill).
# Usage: deploy/deploy.sh            full apply (ConfigMap, Secret, Deployment, Service, Ingress)
#        deploy/deploy.sh code       only refresh the ConfigMap and restart the pod
# Never prints credential values.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HERE/../app"
APP_NAME=dashi
APP_PORT=8080
KUBECTL="$(command -v kubectl || echo "$HOME/.local/bin/kubectl")"

mapfile -t TEAM_CONFIGS < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
(( ${#TEAM_CONFIGS[@]} == 1 )) || { echo "expected exactly one /config/*.config"; exit 1; }
set -a && source "${TEAM_CONFIGS[0]}" && set +a

if [ -z "${KUBECONFIG:-}" ]; then
  for k in /config/kubeconfig /config/"$USERNAME"-k8s.yaml; do
    [ -f "$k" ] && export KUBECONFIG="$k" && break
  done
fi
NS="$USERNAME"
APP_HOST="${INGRESS_URL#http://}"; APP_HOST="${APP_HOST#https://}"; APP_HOST="${APP_HOST%%/*}"
K() { "$KUBECTL" -n "$NS" "$@"; }

SIZE=$(find "$APP_DIR" -maxdepth 1 -type f -printf '%s\n' | awk '{s+=$1} END {print s}')
(( SIZE < 1000000 )) || { echo "app/ is $SIZE bytes; ConfigMap limit is about 1 MiB"; exit 1; }

K create configmap "${APP_NAME}-code" --from-file="$APP_DIR" --dry-run=client -o yaml | K apply -f - >/dev/null
echo "ConfigMap ${APP_NAME}-code updated ($SIZE bytes)"

if [ "${1:-}" = "code" ]; then
  K rollout restart deploy/"$APP_NAME" >/dev/null
  K rollout status deploy/"$APP_NAME" --timeout=240s
  echo "URL: http://${APP_HOST}/app/"
  exit 0
fi

for v in WANDB_API_KEY WANDB_TEAM WANDB_PROJECT; do
  [ -n "${!v:-}" ] || { echo "missing env var $v"; exit 1; }
done
# The pod cannot resolve the public team host, so it talks to the backend Service directly.
# The browser still plays clips through the public host's /api path.
VSS_INTERNAL_URL="${DASHI_VSS_URL:-http://video-backend-service.${NS}.svc.cluster.local:8000}"
K create secret generic "${APP_NAME}-vss-creds" \
  --from-literal=VSS_URL="$VSS_INTERNAL_URL" \
  --from-literal=VSS_USERNAME="$USERNAME" \
  --from-literal=VSS_PASSWORD="$PASSWORD" \
  --from-literal=WANDB_API_KEY="$WANDB_API_KEY" \
  --from-literal=WANDB_TEAM="$WANDB_TEAM" \
  --from-literal=WANDB_PROJECT="$WANDB_PROJECT" \
  --from-literal=DASHI_MODEL="${DASHI_MODEL:-deepseek-ai/DeepSeek-V4-Flash}" \
  --dry-run=client -o yaml | K apply -f - >/dev/null
echo "Secret ${APP_NAME}-vss-creds updated"

K apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${APP_NAME}
  labels: {app: ${APP_NAME}}
spec:
  replicas: 1
  selector:
    matchLabels: {app: ${APP_NAME}}
  template:
    metadata:
      labels: {app: ${APP_NAME}}
    spec:
      containers:
      - name: app
        image: python:3.12-slim
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: ${APP_PORT}
        env:
        - {name: PORT, value: "${APP_PORT}"}
        - {name: PYTHONUNBUFFERED, value: "1"}
        envFrom:
        - secretRef: {name: ${APP_NAME}-vss-creds}
        volumeMounts:
        - {name: code, mountPath: /code}
        workingDir: /code
        command: ["bash", "-c"]
        args:
        - |
          set -euo pipefail
          if [ -f requirements.txt ]; then
            pip install --no-cache-dir -q -r requirements.txt
          fi
          exec python main.py
        readinessProbe:
          httpGet: {path: /health, port: ${APP_PORT}}
          initialDelaySeconds: 10
          periodSeconds: 10
      volumes:
      - name: code
        configMap: {name: ${APP_NAME}-code}
---
apiVersion: v1
kind: Service
metadata:
  name: ${APP_NAME}
  labels: {app: ${APP_NAME}}
spec:
  selector: {app: ${APP_NAME}}
  ports:
  - {name: http, port: 80, targetPort: ${APP_PORT}}
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${APP_NAME}
  labels: {app: ${APP_NAME}}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /\$2
spec:
  ingressClassName: nginx
  rules:
  - host: ${APP_HOST}
    http:
      paths:
      - path: /app(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: ${APP_NAME}
            port: {number: 80}
EOF

K rollout restart deploy/"$APP_NAME" >/dev/null
K rollout status deploy/"$APP_NAME" --timeout=300s
echo "URL: http://${APP_HOST}/app/"
