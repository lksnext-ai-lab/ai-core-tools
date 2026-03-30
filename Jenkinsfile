pipeline {
    agent {
        label "zuvmljenson02"
    }
    
    environment {
        REGISTRY_USER = credentials('lks-docker-registry-user')
        REGISTRY_PASSWORD = credentials('lks-docker-registry-password')
        BACKEND_IMAGE_NAME = "ia-core-tools/ia-core-tools-backend"
        FRONTEND_IMAGE_NAME = "ia-core-tools/ia-core-tools-frontend"
        KUBE_NAMESPACE = "test"
        KUBE_CONFIG = '/home/jenkins/.kube/config'
        IMAGE_KUBECTL = "registry.lksnext.com/bitnami/kubectl:latest"
        INTERNAL_LKS_DOCKER_REGISTRY_URL = "172.20.133.198:8086"

        //Sonar Related
        SONARENTERPRISE_URL = "https://sonarqubeenterprise.devops.lksnext.com/"
        SONARENTERPRISE_TOKEN = credentials('sonarenterprise-analysis-token')
        SONAR_BRANCH = "develop"
        IMAGE_SONARSCANNER = 'registry.lksnext.com/devsecops/custom-sonarscanner-cli:1.0'
        IMAGE_NODE = "registry.lksnext.com/devsecops/node-22:2.0"
        
    }
    
    stages {

        
        stage('Docker login') {
            steps {
                script {
                    sh('docker login $INTERNAL_LKS_DOCKER_REGISTRY_URL -u $REGISTRY_USER -p $REGISTRY_PASSWORD')
                    sh "echo 'Docker login successful'"
                }
            }
        }
        
        stage('Run Tests') {
            steps {
                script {
                    // Start ephemeral test database (tmpfs — no persistent data)
                    sh '''
                        docker run -d --name mattin-test-db \
                            -e POSTGRES_DB=test_db \
                            -e POSTGRES_USER=test_user \
                            -e POSTGRES_PASSWORD=test_pass \
                            -e "POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=C --lc-ctype=C" \
                            -p 5433:5432 \
                            --tmpfs /var/lib/postgresql/data \
                            pgvector/pgvector:pg17
                    '''

                    // Wait for database to be ready
                    sh '''
                        echo "Waiting for test database..."
                        ready=0
                        for i in $(seq 1 30); do
                            if docker exec mattin-test-db pg_isready -U test_user -d test_db; then
                                ready=1
                                break
                            fi
                            sleep 2
                        done
                        if [ "$ready" -ne 1 ]; then
                            echo "Test database did not become ready in time."
                            exit 1
                        fi
                        echo "Test database is ready."
                    '''

                    // Build test runner image
                    sh "docker build --no-cache -f backend/Dockerfile.test -t mattin-test-runner ."

                    // Run tests with JUnit XML and coverage output
                    sh '''
                        mkdir -p test-results
                        docker run --rm \
                            --network host \
                            -e TEST_DATABASE_URL=postgresql://test_user:test_pass@localhost:5433/test_db \
                            -e SQLALCHEMY_DATABASE_URI=postgresql://test_user:test_pass@localhost:5433/test_db \
                            -e AICT_LOGIN=FAKE \
                            -e SECRET_KEY=test-secret-key-32chars-minimum-ok \
                            -e AICT_OMNIADMINS=admin@test.com \
                            -e AICT_MODE=SELF-HOSTED \
                            -e FRONTEND_URL=http://localhost:5173 \
                            -e REPO_BASE_FOLDER=/tmp/test_repos \ 
                            -v "$(pwd)/test-results:/app/test-results" \
                            mattin-test-runner \
                            pytest -v \
                                --junitxml=/app/test-results/junit.xml \
                                --cov=backend \
                                --cov-report=xml:/app/test-results/coverage.xml
                    '''
                }
            }
            post {
                always {
                    // Collect test results for Jenkins UI
                    junit allowEmptyResults: true, testResults: 'test-results/junit.xml'

                    // Cleanup test infrastructure
                    sh 'docker stop mattin-test-db || true'
                    sh 'docker rm mattin-test-db || true'
                    sh 'docker rmi mattin-test-runner || true'
                }
            }
        }
        
        stage('Set Image Tags') {
            steps {
                script {
                    // Read version from pyproject.toml
                    def pyprojectContent = readFile('pyproject.toml')
                    def versionMatch = (pyprojectContent =~ /version = "([^"]+)"/)
                    def version = versionMatch ? versionMatch[0][1] : "latest"
                    
                    // Set image tags for both backend and frontend
                    env.BACKEND_IMAGE_TAG = version
                    env.FRONTEND_IMAGE_TAG = version
                    
                    echo "Backend Image Tag: ${env.BACKEND_IMAGE_TAG}"
                    echo "Frontend Image Tag: ${env.FRONTEND_IMAGE_TAG}"
                }
            }
        }

        stage('Build Backend Docker Image') {
            steps {
                script {
                    // Build with specific version tag
                    sh "docker build --no-cache -f backend/Dockerfile -t ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG} . --build-arg BUILD_DATE=\$(date +%Y-%m-%dT%H:%M:%S)"
                    
                    // Tag as latest as well
                    sh "docker tag ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG} ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:latest"
                    
                    sh "echo 'Backend Docker image built successfully with tags ${BACKEND_IMAGE_TAG} and latest'"
                }
            }
        }

        stage('Build Frontend Docker Image') {
            steps {
                script {
                    // Build with specific version tag
                    sh "docker build --no-cache -f frontend/Dockerfile -t ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG} . --build-arg BUILD_DATE=\$(date +%Y-%m-%dT%H:%M:%S)"
                    
                    // Tag as latest as well
                    sh "docker tag ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG} ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:latest"
                    
                    sh "echo 'Frontend Docker image built successfully with tags ${FRONTEND_IMAGE_TAG} and latest'"
                }
            }
        }

        stage('Sonar') {
            steps {
                script {
                    sh '''
                        docker run --rm \
                        -v ./:/app \
                        -e SONAR_HOST_URL=$SONARENTERPRISE_URL \
                        -e SONAR_TOKEN=$SONARENTERPRISE_TOKEN \
                        $IMAGE_SONARSCANNER \
                        -Dsonar.projectKey=IA-Core-Tools \
                        -Dsonar.projectBaseDir=/app \
                        -Dsonar.sources=/app \
                        -Dsonar.branch.name=$SONAR_BRANCH \
                        -Dsonar.python.version=3.12 \
                        -Dsonar.python.coverage.reportPaths=test-results/coverage.xml
                    '''
                }
            }
        }
        
        stage('Push Backend Docker Image') {
            steps {
                script {
                    // Push specific version
                    sh "docker push ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG}"
                    
                    // Push latest tag
                    sh "docker push ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:latest"
                    
                    sh "echo 'Backend Docker image pushed successfully with tags ${BACKEND_IMAGE_TAG} and latest'"
                }
            }
        }

        stage('Push Frontend Docker Image') {
            steps {
                script {
                    // Push specific version
                    sh "docker push ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG}"
                    
                    // Push latest tag
                    sh "docker push ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:latest"
                    
                    sh "echo 'Frontend Docker image pushed successfully with tags ${FRONTEND_IMAGE_TAG} and latest'"
                }
            }
        }
        
        stage('Deploy to Kubernetes') {
            steps {
                script {
                    echo "Backend Image Tag: ${BACKEND_IMAGE_TAG}"
                    echo "Frontend Image Tag: ${FRONTEND_IMAGE_TAG}"
                    
                    // Update backend image tag in deployment manifest
                    sh "sed -i 's|registry.lksnext.com/${BACKEND_IMAGE_NAME}:.*|registry.lksnext.com/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG}|g' kubernetes/test/backend/deployment.yaml"
                    
                    // Update frontend image tag in deployment manifest
                    sh "sed -i 's|registry.lksnext.com/${FRONTEND_IMAGE_NAME}:.*|registry.lksnext.com/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG}|g' kubernetes/test/frontend/deployment.yaml"
                    
                    // Apply configmap and secrets first
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        apply -f kubernetes/test/configmap.yaml
                    '''
                    sh "echo 'ConfigMap applied successfully'"
                    
                    // Apply backend deployment
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        apply -f kubernetes/test/backend/deployment.yaml
                    '''
                    sh "echo 'Backend deployment applied successfully'"
                    
                    // Apply frontend deployment
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        apply -f kubernetes/test/frontend/deployment.yaml
                    '''
                    sh "echo 'Frontend deployment applied successfully'"
                    
                    // Apply ingress
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        apply -f kubernetes/test/ia-core-tools-ingress-test.yaml
                    '''
                    sh "echo 'Ingress applied successfully'"
                    
                    // Force image pull by annotating deployments with current timestamp
                    sh '''
                        TIMESTAMP=$(date +%s)
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        patch deployment ia-core-tools-backend-test -n $KUBE_NAMESPACE -p "{\\"spec\\":{\\"template\\":{\\"metadata\\":{\\"annotations\\":{\\"deployment.kubernetes.io/revision\\":\\"$TIMESTAMP\\"}}}}}" || echo "Backend deployment does not exist"
                    '''
                    
                    sh '''
                        TIMESTAMP=$(date +%s)
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        patch deployment ia-core-tools-frontend-test -n $KUBE_NAMESPACE -p "{\\"spec\\":{\\"template\\":{\\"metadata\\":{\\"annotations\\":{\\"deployment.kubernetes.io/revision\\":\\"$TIMESTAMP\\"}}}}}" || echo "Frontend deployment does not exist"
                    '''
                    sh "echo 'Deployments patched to force image pull'"
                    
                    // Scale down to 0 replicas first to ensure clean deployment (only if deployments exist)
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        scale deployment/ia-core-tools-backend-test --replicas=0 -n $KUBE_NAMESPACE || echo "Backend deployment does not exist, skipping scale down"
                    '''

                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        scale deployment/ia-core-tools-frontend-test --replicas=0 -n $KUBE_NAMESPACE || echo "Frontend deployment does not exist, skipping scale down"
                    '''

                    // Wait for pods to terminate
                    sh "sleep 30"
                    
                    // Verify no pods are running
                    sh '''
                        echo "Verifying all old pods are terminated..."
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        get pods -n $KUBE_NAMESPACE -l app=ia-core-tools-backend-test --no-headers | wc -l
                    '''

                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        get pods -n $KUBE_NAMESPACE -l app=ia-core-tools-frontend-test --no-headers | wc -l
                    '''
                    
                    // Re-apply deployments to create pods with new images (scale back to desired replicas)
                    sh '''
                        echo "Re-applying backend deployment to restore replicas with new image..."
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        apply -f kubernetes/test/backend/deployment.yaml
                    '''
                    sh "echo 'Backend deployment re-applied successfully'"
                    
                    sh '''
                        echo "Re-applying frontend deployment to restore replicas with new image..."
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        apply -f kubernetes/test/frontend/deployment.yaml
                    '''
                    sh "echo 'Frontend deployment re-applied successfully'"
                    
                    // Wait for backend deployment to be ready
                    sh '''
                        echo "Waiting for backend deployment to be ready..."
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        rollout status deployment/ia-core-tools-backend-test -n $KUBE_NAMESPACE --timeout=300s || echo "Backend deployment rollout failed or does not exist"
                    '''
                    sh "echo 'Backend deployment status checked'"
                    
                    // Wait for frontend deployment to be ready
                    sh '''
                        echo "Waiting for frontend deployment to be ready..."
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        rollout status deployment/ia-core-tools-frontend-test -n $KUBE_NAMESPACE --timeout=300s || echo "Frontend deployment rollout failed or does not exist"
                    '''
                    sh "echo 'Frontend deployment status checked'"
                    
                    // Verify running pods are using the correct image version (only if deployments exist)
                    sh '''
                        echo "Verifying backend pod image version:"
                        if docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        get deployment/ia-core-tools-backend-test -n $KUBE_NAMESPACE >/dev/null 2>&1; then
                            docker run --rm \
                            -v "$(pwd)":/workspace \
                            -v $KUBE_CONFIG:/.kube/config \
                            -w /workspace \
                            $IMAGE_KUBECTL \
                            get pods -n $KUBE_NAMESPACE -l app=ia-core-tools-backend-test -o jsonpath='{.items[*].spec.containers[*].image}'
                        else
                            echo "Backend deployment does not exist"
                        fi
                    '''
                    
                    sh '''
                        echo "Verifying frontend pod image version:"
                        if docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        get deployment/ia-core-tools-frontend-test -n $KUBE_NAMESPACE >/dev/null 2>&1; then
                            docker run --rm \
                            -v "$(pwd)":/workspace \
                            -v $KUBE_CONFIG:/.kube/config \
                            -w /workspace \
                            $IMAGE_KUBECTL \
                            get pods -n $KUBE_NAMESPACE -l app=ia-core-tools-frontend-test -o jsonpath='{.items[*].spec.containers[*].image}'
                        else
                            echo "Frontend deployment does not exist"
                        fi
                    '''
                }
            }
        }

        stage('Clean Docker Images') {
            steps {
                script {
                    // Clean specific version tags
                    sh "docker rmi -f ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG}"
                    sh "docker rmi -f ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG}"
                    
                    // Clean latest tags
                    sh "docker rmi -f ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:latest"
                    sh "docker rmi -f ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:latest"
                    
                    sh "echo 'Docker images cleaned successfully (both version tags and latest)'"
                }
            }
        }
    }
    post {
        success {
            sh "echo 'Pipeline completed successfully'"
        }
        failure {
            sh "echo 'Pipeline failed'"
        }
        always {
            deleteDir()
        }
    }
}