#!/bin/bash
#$0 current command
#$1 scan dir with task ID, but no relative src dir
#$2 scan task ID
#$3 relative source path

#`date +"%S.%M.%H.%d.%m.%y"`
INPUT_V_FILE=$1
SCAN_TASK_ID=$2
OUTPUT_V_FILE=$2
#SRC_DIR=$SCAN_DIR/$3

LOG_PREFIX_INFO="INFO:$0"
LOG_PREFIX_ERROR="ERROR:$0"

echo "***************"
echo "$LOG_PREFIX_INFO: current working directory="`pwd`""
echo "$LOG_PREFIX_INFO: running $0 $*"

#  && [ ! -f $OUTPUT_V_FILE ]
if [ -f $INPUT_V_FILE ]; then
    cat $INPUT_V_FILE | sed "s%scanFile%fileInfos%g" | sed "s%fileno%fileId%g" | sed "s%lineno%lineNo%g" | sed "s%colno%columnNo%g" \
    | sed "s%varname%variableName%g" | sed "s%vulname%vulnerableName%g" | sed "s%errcode%errorCode%g" > $OUTPUT_V_FILE
else
    echo "$LOG_PREFIX_ERROR: [INPUT_V_FILE=$INPUT_V_FILE][SCAN_TASK_ID=$SCAN_TASK_ID][SCAN_DIR=$SCAN_DIR][OUTPUT_V_FILE=$OUTPUT_V_FILE], check pls"
    exit 1
fi


if [ -f $OUTPUT_V_FILE ]; then
    echo "$LOG_PREFIX_INFO: xvsa v file [$OUTPUT_V_FILE] successfully generated"
else
    echo "$LOG_PREFIX_ERROR: xvsa v file [$INPUT_V_FILE] not generated"
    exit 1
fi
