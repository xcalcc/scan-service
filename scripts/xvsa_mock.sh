#!/bin/bash
#$0 current command
#$1 scan dir with task ID, but no relative src dir
#$2 scan task ID
#$3 relative source path

#`date +"%S.%M.%H.%d.%m.%y"`
SCAN_DIR=$1
SCAN_TASK_ID=$2
TASK_TEST_RETURN_V_FILE="$SCAN_DIR/$SCAN_TASK_ID.v"
#SRC_DIR=$SCAN_DIR/$3

LOG_PREFIX_INFO="INFO:$0"
LOG_PREFIX_ERROR="ERROR:$0"

echo "***************"
echo "$LOG_PREFIX_INFO: current working directory=""$(pwd)"
echo "$LOG_PREFIX_INFO: running $0 $*"

#  && [ ! -f $TASK_TEST_RETURN_V_FILE ]
if [ -f $TEST_RETURN_V_FILE ] && [ ! -z "$SCAN_TASK_ID" ] && [ -d $SCAN_DIR ]; then
    cat $TEST_RETURN_V_FILE | sed "s%6d085a75-4182-4ff2-8511-d42544ae76c8%$SCAN_TASK_ID%g" > $TASK_TEST_RETURN_V_FILE
else
    echo "$LOG_PREFIX_ERROR: [TEST_RETURN_V_FILE=$TEST_RETURN_V_FILE][SCAN_TASK_ID=$SCAN_TASK_ID][SCAN_DIR=$SCAN_DIR][TASK_TEST_RETURN_V_FILE=$TASK_TEST_RETURN_V_FILE], check pls"
    exit 1
fi


if [ -f $TASK_TEST_RETURN_V_FILE ]; then
    echo "$LOG_PREFIX_INFO: xvsa v file [$TASK_TEST_RETURN_V_FILE] successfully generated"
else
    echo "$LOG_PREFIX_ERROR: xvsa v file [$TEST_RETURN_V_FILE] not generated"
    exit 1
fi
