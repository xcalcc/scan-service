#!/usr/bin/env bash
#This script is used to deploy scan service with protect xvsa
parallel_xvsa_num=${1:-2}
work_path=${2:-/home/xc5/dev_deploy/scan-service-with-protect-xvsa}
scan_path=${3:-/data0/docker_volume/work}
network_name=${4:-agent-test}
jaeger_host=${5:-192.168.0.129}
docker_host_info=${6:-api:192.168.0.129}
scan_image=${7:-scan.xcalibyte.co:8129/xcalibyte/xcal.xvsa:latest}
issue_api_version=${8:-v2}
kafka_server_host=${9:-192.168.0.129}
scan_service_image=${10:-scan.xcalibyte.co:8129/xcalibyte/xcal.scan-service}
docker_container_port=${11:-8081}
# use to replace the scan_server parameter of xvsa, its default value is 'api'
# when deploy scan service and xvsa docker container by using docker stack,
# these docker container are in the same network with api gateway, api@80 can be correct parsing
xvsa_server_host=${12:-192.168.0.129}
jaeger_port=${13:-6831}


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
	-e SCAN_COMMAND="start.sh" \
	-e SCAN_SERVICE_LOG_PATH=/ws/xcal/app/logs/xcalscan.run.log  \
	-e XVSA_SERVER_HOSTNAME=$xvsa_server_host@80 \
	-e JAEGER_AGENT_HOST=$jaeger_host \
	-e JAEGER_AGENT_PORT=$jaeger_port \
	-e SCAN_IMAGE=$scan_image \
	-e SHARE_SCAN_VOLUME=$scan_path:/share/scan \
	-e ISSUE_API_VERSION=$issue_api_version \
	-e KAFKA_SERVER_HOST=$kafka_server_host \
	-e DOCKER_NETWORK=$network_name \
	-e SCANNER_WORKER_COUNT=$parallel_xvsa_num \
	-v  $scan_path:/share/scan \
	-v  $work_path/logs:/ws/xcal/app/logs  \
	-v  /var/run/docker.sock:/var/run/docker.sock \
      	$scan_service_image bash -c "python3  /ws/xcal/app/scan/scanTaskService/scanApp.py"