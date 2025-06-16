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
        IMAGE_POETRY = "registry.lksnext.com/devsecops/poetry:latest"

        //Sonar Related
        SONARENTERPRISE_URL = "https://sonarqubeenterprise.devops.lksnext.com/"
        SONARENTERPRISE_TOKEN = credentials('sonarenterprise-analysis-token')
        SONAR_BRANCH = "develop"
        IMAGE_NODE = "registry.lksnext.com/devsecops/node-22:2.0"
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        
        stage('Version Management') {
            steps {
                script {
                    // Get current version from pyproject.toml using basic Python
                    def currentVersion = sh(
                        script: '''
                            python3 -c "
                            with open('pyproject.toml', 'r') as f:
                                for line in f:
                                    if 'version = ' in line:
                                        print(line.split('=')[1].strip().strip('\"'))
                                        break
                            "
                            ''',
                        returnStdout: true
                    ).trim()
                    
                    // Get commit message
                    def commitMsg = sh(
                        script: "git log -1 --pretty=%B",
                        returnStdout: true
                    ).trim()
                    
                    // Determine version bump type based on commit message
                    def newVersion
                    if (commitMsg.contains("[major]")) {
                        newVersion = incrementVersion(currentVersion, "major")
                    } else if (commitMsg.contains("[minor]")) {
                        newVersion = incrementVersion(currentVersion, "minor")
                    } else if (commitMsg.contains("[patch]")) {
                        newVersion = incrementVersion(currentVersion, "patch")
                    } else {
                        newVersion = currentVersion
                    }
                    
                    // Update version if needed
                    if (newVersion != currentVersion) {
                        // Update version in pyproject.toml using basic Python
                        sh """
                            python3 -c "
                            with open('pyproject.toml', 'r') as f:
                                lines = f.readlines()
                            with open('pyproject.toml', 'w') as f:
                                for line in lines:
                                    if 'version = ' in line:
                                        f.write('version = \"${newVersion}\"\\n')
                                    else:
                                        f.write(line)
                            "
                            """
                        
                        // Create git tag
                        sh """
                            git config --global user.email "jenkins@lksnext.com"
                            git config --global user.name "Jenkins"
                            git add pyproject.toml
                            git commit -m "Bump version to ${newVersion}"
                            git tag -a "v${newVersion}" -m "Release version ${newVersion}"
                            git push origin HEAD:${env.BRANCH_NAME}
                            git push origin "v${newVersion}"
                        """
                        
                        // Set IMAGE_TAG to new version
                        env.IMAGE_TAG = newVersion
                    } else {
                        // Use current version for IMAGE_TAG
                        env.IMAGE_TAG = currentVersion
                    }
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