#!/usr/bin/env bash
# Deploy Paper Reader to a single-node k3s cluster on this host and expose the
# frontend on NodePort 30080 behind HTTP basic auth. Run on the SERVER, from
# ~/paperreader (which must contain reader_app/, mathtex2text.py,
# reader_app/Dockerfile.tts.pkg). Requires passwordless sudo.
set -euo pipefail
cd "$(dirname "$0")/.."          # -> ~/paperreader (repo-root-like layout)
ROOT="$(pwd)"
NS=paperreader
NODEPORT=30080

echo "==================== 1/7 docker ===================="
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo docker version >/dev/null

echo "==================== 2/7 k3s ===================="
if ! command -v k3s >/dev/null; then
  curl -sfL https://get.k3s.io | sudo sh -
fi
KC="sudo k3s kubectl"
$KC get nodes

echo "==================== 3/7 build backend + tts ===================="
sudo docker build -t pr-backend:latest -f reader_app/Dockerfile.backend "$ROOT"
sudo docker build -t pr-tts:latest     -f reader_app/Dockerfile.tts.pkg "$ROOT"

echo "==================== 4/7 build frontend (+basic auth) ===================="
FE="$ROOT/fe-build"
rm -rf "$FE"; mkdir -p "$FE"
cp reader_app/frontend/index.html reader_app/frontend/style.css reader_app/frontend/app.js "$FE/"
# add basic-auth to the nginx config
sed '/server_name _;/a\    auth_basic "Paper Reader";\n    auth_basic_user_file /etc/nginx/.htpasswd;' \
    reader_app/frontend/nginx.conf > "$FE/nginx.conf"
# generate credentials (user "reader", random password) unless one exists
if [ ! -f "$ROOT/.reader_password" ]; then openssl rand -base64 12 > "$ROOT/.reader_password"; fi
PW="$(cat "$ROOT/.reader_password")"
printf 'reader:%s\n' "$(openssl passwd -apr1 "$PW")" > "$FE/.htpasswd"
cat > "$FE/Dockerfile" <<'DOCKER'
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY .htpasswd /etc/nginx/.htpasswd
COPY index.html style.css app.js /usr/share/nginx/html/
DOCKER
sudo docker build -t pr-frontend:latest "$FE"

echo "==================== 5/7 import images into k3s ===================="
for img in pr-backend pr-tts pr-frontend; do
  sudo docker save "$img:latest" | sudo k3s ctr images import -
done

echo "==================== 6/7 apply manifests ===================="
mkdir -p "$ROOT/k8s-server"
cat > "$ROOT/k8s-server/all.yaml" <<YAML
apiVersion: v1
kind: Namespace
metadata: { name: $NS }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: tts, namespace: $NS }
spec:
  replicas: 1
  selector: { matchLabels: { app: tts } }
  template:
    metadata: { labels: { app: tts } }
    spec:
      enableServiceLinks: false
      containers:
        - name: tts
          image: pr-tts:latest
          imagePullPolicy: Never
          ports: [{ containerPort: 5102 }]
          startupProbe: { httpGet: { path: /health, port: 5102 }, failureThreshold: 40, periodSeconds: 5 }
          readinessProbe: { httpGet: { path: /health, port: 5102 }, periodSeconds: 10 }
          resources: { requests: { cpu: "500m", memory: "1Gi" }, limits: { cpu: "4", memory: "3Gi" } }
---
apiVersion: v1
kind: Service
metadata: { name: tts, namespace: $NS }
spec:
  selector: { app: tts }
  ports: [{ port: 5102, targetPort: 5102 }]
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: backend, namespace: $NS }
spec:
  replicas: 1
  selector: { matchLabels: { app: backend } }
  template:
    metadata: { labels: { app: backend } }
    spec:
      enableServiceLinks: false
      containers:
        - name: backend
          image: pr-backend:latest
          imagePullPolicy: Never
          ports: [{ containerPort: 5101 }]
          env:
            - { name: TTS_URL, value: "http://tts:5102" }
            - { name: READER_PORT, value: "5101" }
          readinessProbe: { httpGet: { path: /api/health, port: 5101 }, periodSeconds: 10 }
          resources: { requests: { cpu: "200m", memory: "512Mi" }, limits: { cpu: "2", memory: "2Gi" } }
---
apiVersion: v1
kind: Service
metadata: { name: backend, namespace: $NS }
spec:
  selector: { app: backend }
  ports: [{ port: 5101, targetPort: 5101 }]
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: frontend, namespace: $NS }
spec:
  replicas: 1
  selector: { matchLabels: { app: frontend } }
  template:
    metadata: { labels: { app: frontend } }
    spec:
      enableServiceLinks: false
      containers:
        - name: frontend
          image: pr-frontend:latest
          imagePullPolicy: Never
          ports: [{ containerPort: 80 }]
          resources: { requests: { cpu: "50m", memory: "32Mi" }, limits: { cpu: "500m", memory: "128Mi" } }
---
apiVersion: v1
kind: Service
metadata: { name: frontend, namespace: $NS }
spec:
  type: NodePort
  selector: { app: frontend }
  ports: [{ port: 80, targetPort: 80, nodePort: $NODEPORT }]
YAML
$KC apply -f "$ROOT/k8s-server/all.yaml"
$KC -n $NS rollout status deploy/tts --timeout=300s
$KC -n $NS rollout status deploy/backend --timeout=180s
$KC -n $NS rollout status deploy/frontend --timeout=120s

echo "==================== 7/7 firewall ===================="
if command -v ufw >/dev/null && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow ${NODEPORT}/tcp || true
fi

IP="$(curl -s -m5 https://api.ipify.org || echo '<server-ip>')"
echo
echo "==================== DONE ===================="
echo "URL:      http://${IP}:${NODEPORT}/"
echo "Login:    reader / ${PW}"
echo "(basic auth over HTTP — credentials are not encrypted without TLS)"
