pipeline {
    agent {
        label "zuvmljenson02"
    }
    
    environment {
        REGISTRY_USER = credentials('lks-docker-registry-user')
        REGISTRY_PASSWORD = credentials('lks-docker-registry-password')
        IMAGE_NAME = "ia-core-tools/ia-core-tools"
        KUBE_NAMESPACE = "test"
        CONTEXT_PATH = "."
        KUBE_CONFIG = '/home/jenkins/.kube/config'
        IMAGE_KUBECTL = "registry.lksnext.com/bitnami/kubectl:latest"
        IMAGE_VERSION_BUMP = "registry.lksnext.com/devsecops/python-version-bumper:0.0.7"
        //INTERNAL_LKS_DOCKER_REGISTRY_URL = "registry.lksnext.com"

        //Sonar Related
        SONARENTERPRISE_URL = "https://sonarqubeenterprise.devops.lksnext.com/"
        SONARENTERPRISE_TOKEN = credentials('sonarenterprise-analysis-token')
        SONAR_BRANCH = "develop"
        IMAGE_NODE = "registry.lksnext.com/devsecops/node-22:2.0"
        GIT_CREDENTIAL = credentials('814b38ca-a572-4188-9c47-ee75ca443903')
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        
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

                        echo "aaa:"
                        for (int i = 0; i < credParts[0].length(); i++) {
                            echo "Character at position ${i}: ${credParts[0][i]}"
                        }
                        
                        echo "aaa:"
                        for (int i = 0; i < credParts[1].length(); i++) {
                            echo "Character at position ${i}: ${credParts[1][i]}"
                        }
                    }
                    
                    def username = credParts[0]
                    def password = credParts[1]
                    
                    sh """
                        docker run --rm \
                        -v "\$(pwd)":/app \
                        -e GITLAB_CREDENTIAL_USER='${username}' \
                        -e GITLAB_CREDENTIAL_PASSWORD='${password}' \
                        $IMAGE_VERSION_BUMP
                    """
                }
            }
        }
        
        stage('Sonar') {
            steps {
                script {
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/app \
                        -e SONAR_HOST_URL=$SONARENTERPRISE_URL \
                        -e SONAR_TOKEN=$SONARENTERPRISE_TOKEN \
                        -e JOB_ACTION=sonar \
                        -e SONAR_BRANCH_NAME=$SONAR_BRANCH \
                        $IMAGE_NODE
                    '''
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    sh "docker build -t ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${IMAGE_NAME}:${IMAGE_TAG} ${CONTEXT_PATH} --build-arg BUILD_DATE=\$(date +%Y-%m-%dT%H:%M:%S)"
                    sh "echo 'Docker image built successfully'"
                }
            }
        }

        stage('Push Docker Image') {
            steps {
                script {
                    sh "docker push ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${IMAGE_NAME}:${IMAGE_TAG}"
                    sh "echo 'Docker image pushed successfully'"
                }
            }
        }
        
        stage('Deploy to Kubernetes') {
            steps {
                script {
                    sh "sed -i 's|${IMAGE_NAME}:.*|${IMAGE_NAME}:${IMAGE_TAG}|g' app/kubernetes/test/app/deployment.yaml"
                    sh "echo 'Tag de la imagen: ${IMAGE_TAG}'"
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        apply -f app/kubernetes/test/app/deployment.yaml
                    '''
                    sh "echo 'Deployment applied successfully'"
                    
                    sh '''
                        docker run --rm \
                        -v "$(pwd)":/workspace \
                        -v $KUBE_CONFIG:/.kube/config \
                        -w /workspace \
                        $IMAGE_KUBECTL \
                        rollout restart deployment/ia-core-tools-app-test -n $KUBE_NAMESPACE
                    '''
                    sh "echo 'Deployment restarted successfully'"
                }
            }
        }

        stage('Clean Docker Images') {
            steps {
                script {
                    sh "docker rmi -f ${INTERNAL_LKS_DOCKER_REGISTRY_URL}/${IMAGE_NAME}:${IMAGE_TAG}"
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

// Helper function to increment version
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