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

        stage('Backend dependency/test preparation') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'python3 -m venv .jenkins-venv && .jenkins-venv/bin/python -m pip install --upgrade pip && .jenkins-venv/bin/python -m pip install -r backend/user-service/requirements.txt'
                    } else {
                        bat 'python -m venv .jenkins-venv && .jenkins-venv\\Scripts\\python.exe -m pip install --upgrade pip && .jenkins-venv\\Scripts\\python.exe -m pip install -r backend\\user-service\\requirements.txt'
                    }
                }
            }
        }

        stage('Unit tests') {
            steps {
                script {
                    if (isUnix()) {
                        sh '.jenkins-venv/bin/python -m pytest tests/unit'
                    } else {
                        bat '.jenkins-venv\\Scripts\\python.exe -m pytest tests\\unit'
                    }
                }
            }
        }

        stage('Frontend build') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'npm ci --prefix frontend/expense-ui && npm --prefix frontend/expense-ui run build'
                    } else {
                        bat 'npm ci --prefix frontend\\expense-ui && npm --prefix frontend\\expense-ui run build'
                    }
                }
            }
        }

        stage('Docker image build') {
            steps {
                withCredentials([
                    string(credentialsId: 'fintrack-jwt-secret', variable: 'JWT_SECRET'),
                    usernamePassword(credentialsId: 'fintrack-mysql-app', usernameVariable: 'MYSQL_APP_USER', passwordVariable: 'MYSQL_APP_PASSWORD'),
                    string(credentialsId: 'fintrack-mysql-root-password', variable: 'MYSQL_ROOT_PASSWORD')
                ]) {
                    script {
                        if (isUnix()) {
                            sh 'docker compose build'
                        } else {
                            bat 'docker compose build'
                        }
                    }
                }
            }
        }

        stage('Docker Compose deployment') {
            steps {
                withCredentials([
                    string(credentialsId: 'fintrack-jwt-secret', variable: 'JWT_SECRET'),
                    usernamePassword(credentialsId: 'fintrack-mysql-app', usernameVariable: 'MYSQL_APP_USER', passwordVariable: 'MYSQL_APP_PASSWORD'),
                    string(credentialsId: 'fintrack-mysql-root-password', variable: 'MYSQL_ROOT_PASSWORD')
                ]) {
                    script {
                        if (isUnix()) {
                            sh 'docker compose up -d --wait'
                        } else {
                            bat 'docker compose up -d --wait'
                        }
                    }
                }
            }
        }

        stage('Health verification') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'curl --fail --silent --show-error http://localhost:8000/health'
                    } else {
                        powershell '$ErrorActionPreference = "Stop"; $response = Invoke-WebRequest -UseBasicParsing http://localhost:8000/health; if ($response.StatusCode -ne 200) { throw "API Gateway health check failed" }; $body = $response.Content | ConvertFrom-Json; if (($body.services.PSObject.Properties.Value | Where-Object { $_ -ne "ok" }).Count -gt 0) { throw "One or more backend services are unhealthy" }; Write-Output $response.Content'
                    }
                }
            }
        }
    }

    post {
        always {
            echo 'Jenkins finished the FinTrack CI/CD pipeline.'
        }
        failure {
            echo 'The build failed. Review the first failed stage and its command output.'
        }
    }
}