#!/bin/bash
#$0 current command
#$1 scan dir with task ID, but no relative src dir
#$2 scan task ID
#$3 relative source path

#`date +"%S.%M.%H.%d.%m.%y"`
# SCAN_DIR=$1
# SCAN_TASK_ID=$2
TASK_RETURN_V_FILE="$SCAN_DIR/$SCAN_TASK_ID.v"
XVSA_SCAN_TOKEN=${SCAN_TOKEN}
XVSA_SCAN_SERVER=${SCAN_SERVER}

#SRC_DIR=$SCAN_DIR/$3

LOG_PREFIX_INFO="INFO:$0"
LOG_PREFIX_ERROR="ERROR:$0"

echo "***************************************"
echo "----- START.SH VERSION 2019-09-02 -----"
echo "$LOG_PREFIX_INFO: current working directory="`pwd`""
echo "$LOG_PREFIX_INFO: running $0"
echo "$LOG_PREFIX_INFO: args : $*"

cd ${SCAN_DIR}
echo "$LOG_PREFIX_INFO: current working directory="`pwd`""
if [ -f preprocess.tar.gz ]; then
    ## Adding this due to a bug in Version 1.0.4.8.18
    export PATH=$PATH:/home/xcalibyte/xvsa/bin
    echo "${LOG_PREFIX_INFO}: [CMD] tar -xzf preprocess.tar.gz -C ${SCAN_TASK_ID}.preprocess"
    echo "${LOG_PREFIX_INFO}: [CMD] tar -xzf preprocess.tar.gz -C ${SCAN_TASK_ID}.preprocess" >> ${SCAN_TASK_ID}.xvsa.log
    tar -xzf preprocess.tar.gz -C ${SCAN_TASK_ID}.preprocess
    echo "${LOG_PREFIX_INFO}: [CMD] xvsa_scan ${SCAN_TASK_ID}.preprocess -token ... -server ..."
    echo "${LOG_PREFIX_INFO}: [CMD] xvsa_scan ${SCAN_TASK_ID}.preprocess -token $XVSA_SCAN_TOKEN -server $XVSA_SCAN_SERVER" >> ${SCAN_TASK_ID}.xvsa.log
    xvsa_scan ${SCAN_TASK_ID}.preprocess -token $XVSA_SCAN_TOKEN -server $XVSA_SCAN_SERVER
    XVSA_SCAN_RET=$?
    if [ -f scan_result.tar.gz ]; then
        # cp -f scan_result/*/xvsa-xfa-dummy.v $TASK_RETURN_V_FILE
        echo "$LOG_PREFIX_INFO: adding $SCAN_TASK_ID to v file $TASK_RETURN_V_FILE"
        find scan_result -name xvsa-xfa-dummy.v | xargs cat | sed "s%@@scanTaskId@@%$SCAN_TASK_ID%g" > ${TASK_RETURN_V_FILE}
    else
        echo "[ scan failed, no scan_result.tar.gz file ]" >> ${SCAN_TASK_ID}.xvsa.failed
        echo "xvsa_scan returned ${XVSA_SCAN_RET}" >> ${SCAN_TASK_ID}.xvsa.failed
        exit $((30+${XVSA_SCAN_RET}))
    fi

# This extraction step is performed by python
elif [ -d ${SCAN_TASK_ID}.preprocess ] && [ -d ${SCAN_TASK_ID}.preprocess/java.scan ]; then
    # Found Fast Agent dir
    echo "${LOG_PREFIX_INFO}: [CMD] bash -x xvsa_scan ${SCAN_TASK_ID}.preprocess"
    echo "${LOG_PREFIX_INFO}: [CMD] xvsa_scan ${SCAN_TASK_ID}.preprocess -token $XVSA_SCAN_TOKEN -server $XVSA_SCAN_SERVER" >> ${SCAN_TASK_ID}.xvsa.log
    bash -x xvsa_scan ${SCAN_TASK_ID}.preprocess -token $XVSA_SCAN_TOKEN -server $XVSA_SCAN_SERVER
    RET=$?
    if [ ${RET} -ne 0 ] ; then
        echo "${LOG_PREFIX_ERROR} xvsa_scan returned ${RET}, aborting... "
        echo "${LOG_PREFIX_ERROR} xvsa_scan returned ${RET}, aborting... " >> ${SCAN_TASK_ID}.xvsa.log
        exit $((30+${RET}))
    fi
    if [ -f scan_result.tar.gz ]; then
        # cp -f scan_result/*/xvsa-xfa-dummy.v $TASK_RETURN_V_FILE
        echo "$LOG_PREFIX_INFO: adding $SCAN_TASK_ID to v file $TASK_RETURN_V_FILE"
        find . -name xvsa-xfa-dummy.v | xargs cat | sed "s%@@scanTaskId@@%$SCAN_TASK_ID%g" > ${TASK_RETURN_V_FILE}
    else
        echo "[ scan failed, no scan_result.tar.gz file ]" >> ${SCAN_TASK_ID}.xvsa.failed
        echo " xvsa_scan returned ${RET}" >> ${SCAN_TASK_ID}.xvsa.failed
        exit $((30+${RET}))
    fi
else
    echo "[ no preprocess.tar.gz file ]" > ${SCAN_TASK_ID}.preprocess.failed
    exit 3
fi

if [ -s ${TASK_RETURN_V_FILE} ]; then
    echo "$LOG_PREFIX_INFO: v file [$TASK_RETURN_V_FILE] successfully generated"
else
    echo "$LOG_PREFIX_ERROR: v file [$TEST_RETURN_V_FILE] not generated or is empty"
    echo "[ $TASK_RETURN_V_FILE not generated or is empty ]" > ${SCAN_TASK_ID}.xvsa.failed
    exit 4
fi
