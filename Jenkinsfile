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
                $images = docker compose config --images

                foreach ($image in $images) {
                    Write-Host "======================================"
                    Write-Host "Scanning image: $image"
                    Write-Host "======================================"

                    trivy image $image

                    if ($LASTEXITCODE -ne 0) {
                        exit $LASTEXITCODE
                    }
                }
            '''
        }
    }
}
      
        stage('Docker Compose Deployment') {
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
                        docker compose up -d --wait
                    '''
                }
            }
        }

        stage('Health Verification') {
            steps {
                powershell '''
                    $ErrorActionPreference = "Stop"

                    Write-Host "Checking FinTrack API Gateway..."

                    $response = Invoke-WebRequest `
                        -UseBasicParsing `
                        http://localhost:8000/health

                    if ($response.StatusCode -ne 200) {
                        throw "API Gateway health check failed."
                    }

                    $body = $response.Content | ConvertFrom-Json

                    Write-Host "Health Response:"
                    Write-Host $response.Content

                    $unhealthy = @(
                        $body.services.PSObject.Properties |
                        Where-Object { $_.Value -ne "ok" }
                    )

                    if ($unhealthy.Count -gt 0) {
                        throw "One or more backend services are unhealthy."
                    }

                    Write-Host "All FinTrack services are healthy."
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
            echo 'Jenkins finished the FinTrack CI/CD pipeline.'
        }

        success {
            echo 'FinTrack CI/CD pipeline completed successfully.'
        }

        failure {
            echo 'FinTrack CI/CD pipeline failed. Check the first failed stage.'
        }
    }
}