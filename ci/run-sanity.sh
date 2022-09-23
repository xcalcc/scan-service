#!/usr/bin/env bash
set -x;
cd $(dirname $0);
export script_dir=$(pwd);
cd ..
work_dir=$(pwd);
echo "WORKDIR : ${work_dir}";
src_main_dir=$(pwd)

## Set up default env vars.
EXTERN_HOME=${src_main_dir}
SCAN_SHARED_PATH=$HOME/shared-scan
SCAN_RESULT_PATH=${EXTERN_HOME}/result

. $script_dir/common.env    # import API_SERVER_HOSTNAME env

DNS_SERVER=$(cat ${script_dir}/DNS_SERVER.conf 2>/dev/null)
# Find local DNS server
if [ -z ${DNS_SERVER} ] ; then
  echo "Using default DNS server"
  DNS_SERVER=$(nmcli device show enp0s5 | grep IP4.GATEWAY | awk '{print $2}')
fi
echo "Using DNS Server by ${DNS_SERVER} .... Please verify if this works"

# Try to ping the dns server to make sure it's working...
ping ${DNS_SERVER} -c 3
PING_RES=$?
if [ ${PING_RES} -ne 0 ] ; then
  echo "Ping DNS server failed... returned ${PING_RES}, check if it is alive, or set another one in ${main_git_dir}/DNS_SERVER.conf";
  exit 1;
fi

# Scandata path
mkdir -p ${SCAN_SHARED_PATH} 2>/dev/null

docker build -t xcalscan-test:latest \
             -f ci/Dockerfile \
             .
ret=$?
if [ $ret -ne 0 ]; then
  echo "Returned zero for docker build";
  exit 3;
fi

docker run \
  -v ${SCAN_SHARED_PATH}:/share/scan \
  -v ${SCAN_RESULT_PATH}:/home/sanity/result \
  --add-host kafka:${API_SERVER_HOSTNAME} \
  xcalscan-test:latest \
  bash -c /home/sanity/ci/docker-entry.sh | tee -a ${work_dir}/docker.run.log

# Change back the permissions.
sudo chown -R $USER ${SCAN_RESULT_PATH}
ret=$?
if [ $ret -ne 0 ]; then
  echo "Returned zero for docker run";
  exit 2;
fi

cat ${work_dir}/docker.run.log | tail -n 1 > ${work_dir}/docker.run.tail.log
if [ -f ${work_dir}/docker.run.tail.log ] ; then
  echo "Found run.tail.log, test passed."
  exit 0;
else
  echo "CTI Sanity test failed, due to not found run.tail.log."
  exit 2;
fi