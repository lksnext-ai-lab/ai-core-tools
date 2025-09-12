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
                    sh "docker build --no-cache -f backend/Dockerfile -t ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG} . --build-arg BUILD_DATE=\$(date +%Y-%m-%dT%H:%M:%S)"
                    sh "echo 'Backend Docker image built successfully'"
                }
            }
        }

        stage('Build Frontend Docker Image') {
            steps {
                script {
                    sh "docker build --no-cache -f frontend/Dockerfile -t ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG} . --build-arg BUILD_DATE=\$(date +%Y-%m-%dT%H:%M:%S)"
                    sh "echo 'Frontend Docker image built successfully'"
                }
            }
        }

        stage('Push Backend Docker Image') {
            steps {
                script {
                    sh "docker push ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG}"
                    sh "echo 'Backend Docker image pushed successfully'"
                }
            }
        }

        stage('Push Frontend Docker Image') {
            steps {
                script {
                    sh "docker push ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG}"
                    sh "echo 'Frontend Docker image pushed successfully'"
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
                    
                    // Restart backend deployment to ensure new image is pulled
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        rollout restart deployment/ia-core-tools-backend-test -n $KUBE_NAMESPACE
                    '''
                    sh "echo 'Backend deployment restarted successfully'"
                    
                    
                    // Restart frontend deployment to ensure new image is pulled
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        rollout restart deployment/ia-core-tools-frontend-test -n $KUBE_NAMESPACE
                    '''
                    sh "echo 'Frontend deployment restarted successfully'"

                    
                    // Verify running pods are using the correct image version
                    sh '''
                        echo "Verifying backend pod image version:"
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        get pods -n $KUBE_NAMESPACE -l app=ia-core-tools-backend-test -o jsonpath='{.items[*].spec.containers[*].image}'
                    '''
                    
                    sh '''
                        echo "Verifying frontend pod image version:"
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        get pods -n $KUBE_NAMESPACE -l app=ia-core-tools-frontend-test -o jsonpath='{.items[*].spec.containers[*].image}'
                    '''
                }
            }
        }

        stage('Clean Docker Images') {
            steps {
                script {
                    sh "docker rmi -f ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${BACKEND_IMAGE_NAME}:${BACKEND_IMAGE_TAG}"
                    sh "docker rmi -f ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${FRONTEND_IMAGE_NAME}:${FRONTEND_IMAGE_TAG}"
                    sh "echo 'Docker images cleaned successfully'"
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