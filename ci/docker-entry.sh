#!/usr/bin/env bash
set -x
cd $(dirname $0)
ci_dir=$(pwd)
cd ..
xcalscan_dir=$(pwd)
result_dir=/home/sanity/result
# Directories
export src_dir=${xcalscan_dir}/scanTaskService/src
export extra_opt=${SANITY_RUN_OPT}

echo "Sanity Test Runner"
echo "xcalscan_dir = ${xcalscan_dir}"
echo "ci_dir = ${ci_dir}"
echo "result_dir = ${result_dir}"

. ${ci_dir}/sanity.env
echo "--------------------------------------"
printenv;
echo "--------------------------------------"
cd ${result_dir} || exit 2
python3 ${src_dir}/tests/test_AutomatedTest.py | tee -a xcalscan.test.log
ret=$?
if [ $ret -ne 0 ] ; then
  echo "Python Xcalscan test driver reported error"
  exit 2;
else
  echo "Test passed"
  exit 0;
fi


