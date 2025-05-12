pipeline {
    agent {
        label "zuvmljenson02"
    }
    
    environment {
        SONARENTERPRISE_TOKEN = credentials('sonarenterprise-analysis-token')
        SONARENTERPRISE_URL = "https://sonarqubeenterprise.devops.lksnext.com/"
        SONAR_BRANCH = "develop"
        REGISTRY_USER = credentials('lks-docker-registry-user')
        REGISTRY_PASSWORD = credentials('lks-docker-registry-password')
        IMAGE_NAME = "ia-core-tools/ia-core-tools"
        KUBE_NAMESPACE = "test"
        CONTEXT_PATH = "."
        KUBE_CONFIG = '/home/jenkins/.kube/config'
        IMAGE_KUBECTL = "registry.lksnext.com/bitnami/kubectl:latest"
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
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
                        -e CHECK_QG=$CHECK_QG \
                        -e SONAR_BRANCH_NAME=$SONAR_BRANCH \
                        $IMAGE_NODE \
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

        stage('Docker login') {
            steps {
                script {
                    sh('docker login $INTERNAL_LKS_DOCKER_REGISTRY_URL -u $REGISTRY_USER -p $REGISTRY_PASSWORD')
                    sh "echo 'Docker login successful'"
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