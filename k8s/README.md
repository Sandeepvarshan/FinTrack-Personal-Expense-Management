# FinTrack on Minikube

This folder deploys the existing Dockerized FinTrack application to a local Kubernetes
cluster. The existing `docker-compose.yml` is unchanged and remains the source for local
Compose deployment.

## Kubernetes layout

All resources are in the `fintrack` namespace.

| Component | Kubernetes Service | Port | Type |
|---|---|---:|---|
| MySQL | `mysql` | 3306 | ClusterIP |
| User Service | `user-service` | 8001 | ClusterIP |
| Expense Service | `expense-service` | 8002 | ClusterIP |
| Category Service | `category-service` | 8003 | ClusterIP |
| Budget Service | `budget-service` | 8004 | ClusterIP |
| Report Service | `report-service` | 8005 | ClusterIP |
| Notification Service | `notification-service` | 8006 | ClusterIP |
| API Gateway | `api-gateway` | 8000 | ClusterIP |
| Frontend | `frontend` | 80 | NodePort 30080 |

The frontend is the only externally exposed application service. Its existing Nginx
configuration proxies `/api/` to `api-gateway:8000`. The gateway uses the Kubernetes
service names for all backend calls. Expense uses `budget-service:8004`, Budget uses
`notification-service:8006`, and all database-backed services use `mysql:3306`.

MySQL data is stored in the `mysql-data` PersistentVolumeClaim. Do not delete this PVC
if the data should survive Pod recreation.

## Prerequisites

Install and verify:

```powershell
minikube version
kubectl version --client
```

The Dockerfiles use these Minikube-local image tags:

```text
fintrack/mysql:minikube
fintrack/user-service:minikube
fintrack/expense-service:minikube
fintrack/category-service:minikube
fintrack/budget-service:minikube
fintrack/report-service:minikube
fintrack/notification-service:minikube
fintrack/api-gateway:minikube
fintrack/frontend:minikube
```

## Build images into Minikube

Start Minikube first. Each command builds from the existing Dockerfile and repository
root context:

```powershell
minikube start --driver=docker

minikube image build -t fintrack/mysql:minikube -f database/Dockerfile .
minikube image build -t fintrack/user-service:minikube -f backend/user-service/Dockerfile .
minikube image build -t fintrack/expense-service:minikube -f backend/expense-service/Dockerfile .
minikube image build -t fintrack/category-service:minikube -f backend/category-service/Dockerfile .
minikube image build -t fintrack/budget-service:minikube -f backend/budget-service/Dockerfile .
minikube image build -t fintrack/report-service:minikube -f backend/report-service/Dockerfile .
minikube image build -t fintrack/notification-service:minikube -f backend/notification-service/Dockerfile .
minikube image build -t fintrack/api-gateway:minikube -f backend/api-gateway/Dockerfile .
minikube image build -t fintrack/frontend:minikube -f frontend/expense-ui/Dockerfile .
```

Confirm they are available:

```powershell
minikube image ls | Select-String fintrack
```

## Create the namespace and Secret

Create the namespace first:

```powershell
kubectl apply -f k8s/namespace.yaml
```

`k8s/mysql/secret.yaml` is a safe template containing placeholders only. Do not put real
passwords or JWT secrets in Git. For local use, copy it to the ignored file, replace the
placeholder values in that local copy, and apply the local copy:

```powershell
Copy-Item k8s/mysql/secret.yaml k8s/mysql/secret.local.yaml
notepad k8s/mysql/secret.local.yaml
kubectl apply -f k8s/mysql/secret.local.yaml
```

The Secret must contain these keys:

```text
root-password
app-user
app-password
jwt-secret
```

Use the same database application user, application password, and shared JWT secret for
all services. The application database name is `expense_tracker` and the application user
is `expense_tracker_app`, matching the existing Compose configuration. Never print Secret
values in a terminal transcript.

## Deploy in order

Create MySQL storage and Service:

```powershell
kubectl apply -f k8s/mysql/pvc.yaml
kubectl apply -f k8s/mysql/service.yaml
kubectl apply -f k8s/mysql/deployment.yaml
kubectl wait --for=condition=available deployment/mysql -n fintrack --timeout=180s
kubectl wait --for=condition=ready pod -l app=mysql -n fintrack --timeout=180s
```

Deploy the six backend services:

```powershell
kubectl apply -f k8s/user-service/
kubectl apply -f k8s/expense-service/
kubectl apply -f k8s/category-service/
kubectl apply -f k8s/budget-service/
kubectl apply -f k8s/report-service/
kubectl apply -f k8s/notification-service/
kubectl wait --for=condition=available deployment --all -n fintrack --timeout=180s
```

Deploy the gateway and frontend:

```powershell
kubectl apply -f k8s/api-gateway/
kubectl wait --for=condition=available deployment/api-gateway -n fintrack --timeout=180s
kubectl apply -f k8s/frontend/
kubectl wait --for=condition=available deployment/frontend -n fintrack --timeout=180s
```

## Inspect the deployment

```powershell
kubectl get pods -n fintrack -o wide
kubectl get deployments -n fintrack
kubectl get services -n fintrack
kubectl get pvc -n fintrack
kubectl get endpoints -n fintrack
```

Inspect a failing Pod:

```powershell
kubectl describe pod <pod-name> -n fintrack
kubectl logs <pod-name> -n fintrack
kubectl logs deployment/<deployment-name> -n fintrack
```

Check the gateway from inside the cluster:

```powershell
kubectl run gateway-check -n fintrack --rm -i --restart=Never --image=curlimages/curl:8.10.1 -- curl --fail http://api-gateway:8000/health
```

Access the frontend through Minikube:

```powershell
minikube service frontend -n fintrack --url
```

Open the printed URL in a browser. The frontend's `/api/health` path should reach the
gateway through the existing Nginx proxy.

## Validate manifests without applying them

```powershell
kubectl apply --dry-run=client -f k8s/namespace.yaml
kubectl apply --dry-run=client -f k8s/mysql/
kubectl apply --dry-run=client -f k8s/user-service/
kubectl apply --dry-run=client -f k8s/expense-service/
kubectl apply --dry-run=client -f k8s/category-service/
kubectl apply --dry-run=client -f k8s/budget-service/
kubectl apply --dry-run=client -f k8s/report-service/
kubectl apply --dry-run=client -f k8s/notification-service/
kubectl apply --dry-run=client -f k8s/api-gateway/
kubectl apply --dry-run=client -f k8s/frontend/
```

## Files not to commit

Do not commit:

```text
k8s/mysql/secret.local.yaml
.env
backend/*/.env
```

The tracked `k8s/mysql/secret.yaml` is a placeholder template, not a production Secret.