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
        IMAGE_VERSION_BUMP = "registry.lksnext.com/devsecops/python-version-bumper:0.0.12"
        INTERNAL_LKS_DOCKER_REGISTRY_URL = "172.20.133.198:8086"

        //Sonar Related
        SONARENTERPRISE_URL = "https://sonarqubeenterprise.devops.lksnext.com/"
        SONARENTERPRISE_TOKEN = credentials('sonarenterprise-analysis-token')
        SONAR_BRANCH = "develop"
        IMAGE_SONARSCANNER = 'registry.lksnext.com/devsecops/custom-sonarscanner-cli:1.0'
        IMAGE_NODE = "registry.lksnext.com/devsecops/node-22:2.0"
        GIT_CREDENTIAL = credentials('814b38ca-a572-4188-9c47-ee75ca443903')
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
        
        stage('Version Bump') {
            steps {
                script {
                    echo "Debugging credentials..."
                    echo "GIT_CREDENTIAL exists: ${GIT_CREDENTIAL != null}"
                    echo "GIT_CREDENTIAL length: ${GIT_CREDENTIAL.length()}"
                    echo "GIT_CREDENTIAL type: ${GIT_CREDENTIAL.getClass().getName()}"
                    
                    // Split credentials and check parts
                    def credParts = GIT_CREDENTIAL.split(':')
                    echo "Number of credential parts: ${credParts.length}"
                    if (credParts.length >= 2) {
                        echo "Username part exists: ${credParts[0] != null}"
                        echo "Username length: ${credParts[0].length()}"
                        echo "Password part exists: ${credParts[1] != null}"
                        echo "Password length: ${credParts[1].length()}"

                    }
                    
                    def username = credParts[0]
                    def password = credParts[1]
                    
                    sh """
                        docker run --rm \
                        -v "\$(pwd)":/app \
                        -e GITLAB_CREDENTIAL_USER=${username} \
                        -e GITLAB_CREDENTIAL_PASSWORD=${password} \
                        -e TEST=testAAAABC \
                        $IMAGE_VERSION_BUMP
                    """
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
            when {
                environment name: 'JOB_ACTION', value: 'sonar'
            }
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
                        -Dsonar.python.version=3.12
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

def incrementVersion(String version, String type) {
    def parts = version.split("\\.")
    if (type == "major") {
        return "${parts[0].toInteger() + 1}.0.0"
    } else if (type == "minor") {
        return "${parts[0]}.${parts[1].toInteger() + 1}.0"
    } else if (type == "patch") {
        return "${parts[0]}.${parts[1]}.${parts[2].toInteger() + 1}"
    }
    return version
}