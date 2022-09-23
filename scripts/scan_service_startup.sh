#!/usr/bin/env bash
#This script is used to deploy scan service with no protect xvsa
work_path=${1:-/home/xc5/dev_deploy/scan-service}
scan_path=${2:-/data0/docker_volume/work}
network_name=${3:-agent-test}
jaeger_host=${4:-192.168.0.129}
docker_host_info=${5:-api:192.168.0.129}
scan_image=${6:-10.10.2.117:5000/gcc.javac.maven.xcalmake.xvsa:0.1.1}
issue_api_version=${7:-v2}
kafka_server_host=${8:-192.168.0.129}
scan_service_image=${9:-scan.xcalibyte.co:8129/xcalibyte/xcal.scan-service}
docker_container_port=${10:-8081}
share_docker_scripts_dir=${11:-/home/xc5/dev_deploy/scan-service/backup/docker}

scan_service_container=dev_scan_service
if docker ps | grep $scan_service_container > /dev/null; then
  docker rm -f $scan_service_container
fi
docker run -d --name $scan_service_container -p $docker_container_port:80 \
    --restart=always \
	--add-host $docker_host_info \
	--network $network_name \
	--log-opt max-size=10m --log-opt max-file=5 \
	-e PYTHONPATH=/ws/xcal/app/scan/scanTaskService/commondef/src:/ws/xcal/app/scan:${PYTHONPATH} \
	-e WS_XCAL_APP=/ws/xcal/app/scan/scanTaskService/scanApp.py \
	-e SCAN_COMMAND="bash -x /ws/xcal/app/scan/docker/generic-gcc-make/start.sh" \
	-e SCAN_SERVICE_LOG_PATH=/ws/xcal/app/logs/xcalscan.run.log  \
	-e JAEGER_AGENT_HOST=$jaeger_host \
	-e SCAN_IMAGE=$scan_image \
	-e SHARE_XVSA_VOLUME=$work_path/xvsa:/home/xcalibyte/xvsa \
	-e SHARE_WS_APP_VOLUME=${share_docker_scripts_dir}:/ws/xcal/app/scan/docker \
	-e SHARE_SCAN_VOLUME=$scan_path:/share/scan \
	-e ISSUE_API_VERSION=$issue_api_version \
	-e KAFKA_SERVER_HOST=$kafka_server_host \
	-e DOCKER_NETWORK=$network_name \
	-v  $scan_path:/share/scan \
	-v  $work_path/logs:/ws/xcal/app/logs  \
	-v  /var/run/docker.sock:/var/run/docker.sock \
      	$scan_service_image bash -c "python3  /ws/xcal/app/scan/scanTaskService/scanApp.py"