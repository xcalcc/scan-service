pipeline {
    agent {
        docker {
            image 'python:3.5.2'
            args '-v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker'
        }
    }
    environment {
        SCAN_IMAGE = "scan.xcalibyte.co:8129/xcalibyte/xcal.scan-service";
        IMAGE_VERSION = "v_${BUILD_NUMBER}"
    }
    stages {
        stage('install_requirements') {
            steps {
                echo '========= install requirements to python docker container =========='
                sh 'python --version'
                sh 'pip3 install requests flask docker prometheus-client kafka-python jaeger-client -i https://mirrors.aliyun.com/pypi/simple/'
            }
        }
        stage('pull_xcalscan') {
            steps {
                echo '========= pull_xcalscan =========='
                checkout([$class: 'GitSCM', branches: [[name: '*/dev']],
                          doGenerateSubmoduleConfigurations: false,
                          extensions: [[$class: 'SubmoduleOption', disableSubmodules: false, parentCredentials: true, recursiveSubmodules: true, reference: '', trackingSubmodules: false]],
                          submoduleCfg: [],
                          userRemoteConfigs: [[credentialsId: 'gitlab_xc5sdlcbot', url: 'https://gitlab.com/xc5sz/xcalscan.git']]
                          ])
            }
        }
        stage('unittest') {
            steps {
                echo '========== unittest =========='
                sh '''
                export PYTHONPATH="/var/jenkins_home/workspace/python-scan-service/scanTaskService/src:/var/jenkins_home/workspace/python-scan-service/scanTaskService/src/scanTaskService/commondef/src"
                export TEST_AGENT_USER=xc5
                export TEST_AGENT_ADDR=dev_agent_service
                export TEST_CPP_AGENT_ADDR=dev_agent_service
                export PYTHONUNBUFFERED=1
                export JAEGER_AGENT_HOST=127.0.0.1
                export SCAN_PORT=6550
                export SHARE_SCAN_VOLUME=/share/scan:/share/scan
                export SCAN_COMMAND=start.sh
                export SCAN_IMAGE=xcal.xvsa:latest
                export KAFKA_SERVER_HOST=localhost:9092
                export API_SERVER_HOSTNAME=127.0.0.1
                export DEFAULT_LOG_LEVEL=INFO
                export TEST_TOKEN=eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI5Y2E2MGY1NS1mNjlmLTRmNDAtOTI5My1jNDYyNDdjNzNiNTYiLCJpYXQiOjE1NzI1Mjg1MTEsImV4cCI6MTU3MjYxNDkxMX0.HBQGJegPgrUqCvFUfxT2Pdq26y8Xlz-MAIn012e8kvOmRIW0CRQkGzsMhUSjNs-1xPMcULfq6jjiA-GnzMhFiw
                cd /var/jenkins_home/workspace/python-scan-service/scanTaskService/src/tests
                exit 0
                '''
            }
        }
        stage('deploy') {
            steps {
                echo '========== deploy =========='
                script {
                  echo env.ssh_server_name
                  commitTime = getFormattedCommitTime()
                  shortCommitHash = getShortCommitHash()
                  IMAGE_VERSION = commitTime + "." + shortCommitHash
                  echo "${IMAGE_VERSION}"
                  withCredentials([usernamePassword(credentialsId: 'harbor_xc5sdlcbot', passwordVariable: 'password', usernameVariable:'user')]) {
                    sh """
                    docker login -u $user -p $password scan.xcalibyte.co:8129
                    docker build -t $SCAN_IMAGE:${IMAGE_VERSION} -f scanTaskService/docker/ws.scan.Dockerfile .
                    docker tag $SCAN_IMAGE:${IMAGE_VERSION} $SCAN_IMAGE:latest
                    docker push $SCAN_IMAGE:latest
                    docker push $SCAN_IMAGE:${IMAGE_VERSION}
                    """
                  }
                  sshPublisher(
                   continueOnError: false, failOnError: true,
                   publishers: [
                    sshPublisherDesc(
                     configName: "${env.ssh_server_name}",
                     verbose: true,
                     transfers: [
                      sshTransfer(
                       sourceFiles:"scripts/scan_service_startup_with_protected_xvsa.sh",
                       removePrefix:"scripts",
                       remoteDirectory: "$file_path_on_destination_machine",
                       execCommand: "cd ${work_path} && docker pull $SCAN_IMAGE:latest && sh scan_service_startup_with_protected_xvsa.sh $parallel_xvsa_num"
                      )
                    ])
                  ])

                  sleep 5
                  script{
                    try{
                        build job: 'xcalscan-deploy', propagate: true, wait: false
                    }
                    catch (err){
                        unstable('Calling next job failed, job: xcalscan-deploy, set result to unstable')
                        echo "Error caught: ${err}"
                    }
                }
                }
            }
        }
    }
}

def getShortCommitHash() {
    return sh(returnStdout: true, script: "git log -n 1 --pretty=format:'%h'").trim()
}

def getCommitTime() {
    return sh(returnStdout: true, script: "git log -1 | grep ^Date: |awk '{\$1=\"\"; \$NF=\"\"; print}'").trim()
}

def getFormattedCommitTime() {
    def commitTime = getCommitTime()
    return sh(returnStdout: true, script: "date --date=\"${commitTime}\" '+%Y%m%d-%H%M%S'").trim()
}

def getCurrentBranch () {
    return sh (
            script: 'git rev-parse --abbrev-ref HEAD',
            returnStdout: true
    ).trim()
}