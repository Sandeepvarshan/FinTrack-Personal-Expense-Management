pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Backend Dependency Preparation') {
            steps {
                bat '''
                    python -m venv .jenkins-venv
                    .jenkins-venv\\Scripts\\python.exe -m pip install --upgrade pip
                    .jenkins-venv\\Scripts\\python.exe -m pip install -r backend\\user-service\\requirements.txt
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                bat '''
                    .jenkins-venv\\Scripts\\python.exe -m pytest tests\\unit
                '''
            }
        }

        stage('Frontend Build') {
            steps {
                bat '''
                    npm ci --prefix frontend\\expense-ui
                    npm --prefix frontend\\expense-ui run build
                '''
            }
        }

        stage('Docker Image Build') {
            steps {
                withCredentials([
                    string(
                        credentialsId: 'fintrack-jwt-secret',
                        variable: 'JWT_SECRET'
                    ),
                    usernamePassword(
                        credentialsId: 'fintrack-mysql-app',
                        usernameVariable: 'MYSQL_APP_USER',
                        passwordVariable: 'MYSQL_APP_PASSWORD'
                    ),
                    string(
                        credentialsId: 'fintrack-mysql-root-password',
                        variable: 'MYSQL_ROOT_PASSWORD'
                    )
                ]) {
                    bat '''
                        docker compose build
                    '''
                }
            }
        }

        stage('Trivy Security Scan') {
            steps {
                withCredentials([
                    string(
                        credentialsId: 'fintrack-jwt-secret',
                        variable: 'JWT_SECRET'
                    ),
                    usernamePassword(
                        credentialsId: 'fintrack-mysql-app',
                        usernameVariable: 'MYSQL_APP_USER',
                        passwordVariable: 'MYSQL_APP_PASSWORD'
                    ),
                    string(
                        credentialsId: 'fintrack-mysql-root-password',
                        variable: 'MYSQL_ROOT_PASSWORD'
                    )
                ]) {
                    powershell '''
                        $ErrorActionPreference = "Stop"

                        $images = docker compose config --images

                        foreach ($image in $images) {

                            Write-Host "======================================"
                            Write-Host "Scanning image: $image"
                            Write-Host "======================================"

                            trivy image $image

                            if ($LASTEXITCODE -ne 0) {
                                throw "Trivy scan failed for image: $image"
                            }
                        }

                        Write-Host "All Docker images passed the Trivy scan execution."
                    '''
                }
            }
        }

        stage('Refresh Minikube Context') {
            steps {
                bat '''
                    minikube update-context -p minikube
                    kubectl config current-context
                '''
            }
        }

        stage('Verify Kubernetes Access') {
            steps {
                bat '''
                    kubectl get nodes
                '''
            }
        }

        stage('Prepare Images for Kubernetes') {
            steps {
                bat '''
                    docker tag fintrack-ci-cd-mysql fintrack/mysql:minikube
                    docker tag fintrack-ci-cd-user-service fintrack/user-service:minikube
                    docker tag fintrack-ci-cd-expense-service fintrack/expense-service:minikube
                    docker tag fintrack-ci-cd-category-service fintrack/category-service:minikube
                    docker tag fintrack-ci-cd-budget-service fintrack/budget-service:minikube
                    docker tag fintrack-ci-cd-report-service fintrack/report-service:minikube
                    docker tag fintrack-ci-cd-notification-service fintrack/notification-service:minikube
                    docker tag fintrack-ci-cd-api-gateway fintrack/api-gateway:minikube
                    docker tag fintrack-ci-cd-frontend fintrack/frontend:minikube
                '''
            }
        }

        stage('Load Images into Minikube') {
            steps {
                bat '''
                    minikube image load fintrack/mysql:minikube
                    minikube image load fintrack/user-service:minikube
                    minikube image load fintrack/expense-service:minikube
                    minikube image load fintrack/category-service:minikube
                    minikube image load fintrack/budget-service:minikube
                    minikube image load fintrack/report-service:minikube
                    minikube image load fintrack/notification-service:minikube
                    minikube image load fintrack/api-gateway:minikube
                    minikube image load fintrack/frontend:minikube
                '''
            }
        }

        stage('Kubernetes Deployment') {
            steps {
                bat '''
                    kubectl apply -f k8s\\namespace.yaml
                    kubectl apply -f k8s\\mysql\\
                    kubectl apply -f k8s\\user-service\\
                    kubectl apply -f k8s\\expense-service\\
                    kubectl apply -f k8s\\category-service\\
                    kubectl apply -f k8s\\budget-service\\
                    kubectl apply -f k8s\\report-service\\
                    kubectl apply -f k8s\\notification-service\\
                    kubectl apply -f k8s\\api-gateway\\
                    kubectl apply -f k8s\\frontend\\
                '''
            }
        }

        stage('Kubernetes Rollout Verification') {
            steps {
                bat '''
                    kubectl rollout status deployment/mysql -n fintrack --timeout=180s
                    kubectl rollout status deployment/user-service -n fintrack --timeout=180s
                    kubectl rollout status deployment/expense-service -n fintrack --timeout=180s
                    kubectl rollout status deployment/category-service -n fintrack --timeout=180s
                    kubectl rollout status deployment/budget-service -n fintrack --timeout=180s
                    kubectl rollout status deployment/report-service -n fintrack --timeout=180s
                    kubectl rollout status deployment/notification-service -n fintrack --timeout=180s
                    kubectl rollout status deployment/api-gateway -n fintrack --timeout=180s
                    kubectl rollout status deployment/frontend -n fintrack --timeout=180s
                '''
            }
        }

        stage('Kubernetes Health Verification') {
            steps {
                powershell '''
                    $ErrorActionPreference = "Stop"

                    Write-Host "======================================"
                    Write-Host "FinTrack Kubernetes Health Check"
                    Write-Host "======================================"

                    kubectl get pods -n fintrack
                    kubectl get services -n fintrack

                    Write-Host ""
                    Write-Host "Checking API Gateway health from inside Kubernetes..."

                    $response = kubectl exec deployment/api-gateway -n fintrack -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"

                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to execute API Gateway health check."
                    }

                    Write-Host "Health Response:"
                    Write-Host $response

                    $health = $response | ConvertFrom-Json

                    if ($health.status -ne "ok") {
                        throw "API Gateway health status is not OK."
                    }

                    $unhealthy = @(
                        $health.services.PSObject.Properties |
                        Where-Object {
                            $_.Value -ne "ok"
                        }
                    )

                    if ($unhealthy.Count -gt 0) {
                        throw "One or more FinTrack backend services are unhealthy."
                    }

                    Write-Host ""
                    Write-Host "All FinTrack Kubernetes services are healthy."
                '''
            }
        }

        stage('Frontend Port Forward') {
            steps {
                powershell '''
                    $ErrorActionPreference = "Stop"

                    Write-Host "Starting Kubernetes frontend port-forward..."

                    $portForwardProcess = Start-Process `
                        -FilePath "kubectl.exe" `
                        -ArgumentList "port-forward -n fintrack service/frontend 5173:80" `
                        -PassThru `
                        -WindowStyle Hidden

                    Start-Sleep -Seconds 8

                    if ($portForwardProcess.HasExited) {
                        throw "Frontend port-forward process exited unexpectedly."
                    }

                    Write-Host "Frontend available at http://localhost:5173"

                    Set-Content `
                        -Path "frontend-port-forward.pid" `
                        -Value $portForwardProcess.Id
                '''
            }
        }

        stage('Playwright E2E Tests') {
            steps {
                bat '''
                    npm ci
                    npx playwright install chromium
                    npm run e2e
                '''
            }
        }
    }

    post {

        always {
            powershell '''
                if (Test-Path "frontend-port-forward.pid") {

                    $portForwardPid = Get-Content "frontend-port-forward.pid"

                    if ($portForwardPid) {

                        Write-Host "Stopping Kubernetes frontend port-forward..."

                        Stop-Process `
                            -Id ([int]$portForwardPid) `
                            -Force `
                            -ErrorAction SilentlyContinue
                    }

                    Remove-Item `
                        "frontend-port-forward.pid" `
                        -Force `
                        -ErrorAction SilentlyContinue
                }

                Write-Host ""
                Write-Host "======================================"
                Write-Host "Final Kubernetes State"
                Write-Host "======================================"

                kubectl get pods -n fintrack
                kubectl get services -n fintrack
            '''

            echo 'Jenkins finished the FinTrack CI/CD pipeline.'
        }

        success {
            echo 'FinTrack CI/CD pipeline with Kubernetes completed successfully.'
        }

        failure {
            echo 'FinTrack CI/CD pipeline failed. Check the first failed stage.'
        }
    }
}