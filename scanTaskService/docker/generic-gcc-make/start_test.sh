#!/bin/bash
#$0 current command
#$1 scan dir with task ID, but no relative src dir
#$2 scan task ID
#$3 relative source path

#`date +"%S.%M.%H.%d.%m.%y"`
# SCAN_DIR=$1
# SCAN_TASK_ID=$2
TASK_RETURN_V_FILE="$SCAN_DIR/$SCAN_TASK_ID.v"
#SRC_DIR=$SCAN_DIR/$3

LOG_PREFIX_INFO="INFO:$0"
LOG_PREFIX_ERROR="ERROR:$0"

echo "***************"
echo "$LOG_PREFIX_INFO: current working directory="`pwd`""
echo "$LOG_PREFIX_INFO: running $0 $@"

#  && [ ! -f $TASK_RETURN_V_FILE ]
if [ ! -z "$SCAN_TASK_ID" ] && [ -d $SCAN_DIR ]; then
    cd $SCAN_DIR
    echo "$LOG_PREFIX_INFO: current working directory="`pwd`" $SCAN_TASK_ID, $SCAN_DIR"    
    # rm -fr $SCAN_TASK_ID.*; mkdir $SCAN_TASK_ID.preprocess
    # make clean
    # xcalmake make
    # if [ -f preprocess.tar.gz ]; then
    #     tar -xzvf preprocess.tar.gz -C $SCAN_TASK_ID.preprocess
    #     xvsa_scan $SCAN_TASK_ID.preprocess
    #     if [ -f scan_result.tar.gz ]; then 
    #         cp -f scan_result/*/xvsa-xfa-dummy.v $TASK_RETURN_V_FILE
    #     else
    #         echo "[ -f scan_result.tar.gz ]" > $SCAN_TASK_ID.xvsa.failed
    #         exit 1
    #     fi
    # else
    #     echo "[ -f preprocess.tar.gz ]" > $SCAN_TASK_ID.preprocess.failed
    #     exit 1
    # fi
else
    # echo "[ ! -z "$SCAN_TASK_ID" ] && [ -d $SCAN_DIR ]" >  $SCAN_TASK_ID.start.failed
    echo "$LOG_PREFIX_ERROR: [ ! -z "$SCAN_TASK_ID" ] && [ -d $SCAN_DIR ] failed"
    exit 1
fi


if [ -f $TASK_RETURN_V_FILE ]; then
    echo "$LOG_PREFIX_INFO: xvsa v file [$TASK_RETURN_V_FILE] successfully generated"
else
    echo "$LOG_PREFIX_ERROR: xvsa v file [$TEST_RETURN_V_FILE] not generated"
    # echo "[ -f $TASK_RETURN_V_FILE ]" > $SCAN_TASK_ID.xvsa.failed    
    exit 1
fi
