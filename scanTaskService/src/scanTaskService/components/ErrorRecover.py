#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import time
import datetime
from enum import Enum, unique
import psutil
from scanTaskService.Config import ROOT_DIR


class CONST_STR(Enum):
    FILE_INFO = "fileinfo.json"
    SCAN_TASK_LOG = "scan_task.log"
    PREPROCESS_TGZ = "preprocess.tar.gz"
    RECOVER_POLICY = os.path.join(ROOT_DIR, 'RecoverPolicy.json')
    XCALSCAN_FOLDER = "../.xcalscan"


class ERROR(Exception):
    pass


# PRE_SCM is sub phase of preprocess
class E_PRE_SCM_FAILURE(ERROR):
    def __init__(self, ErrMsg):
        self.ErrMsg = ErrMsg

    def __str__(self):
        return repr(self.ErrMsg)


class E_PRE_SCM_TIMEOUT(ERROR):
    pass


@unique
class SETUP(Enum):
    PROJ_CONF = 0
    CR_PROJ = 1
    SCM_SRC = 2


@unique
class PREPROC(Enum):
    PREP_SRC = 8
    GET_SRC = 9
    BUILD = 10
    UP_FILE = 11
    SP_COMMIT_ID = 12
    SP_SCM_DIFF = 13
    SP_SRC_ZIP = 14


@unique
class PROC(Enum):
    ENGINE_MERGE = 16
    VTXTDIFF = 17
    V2CSF = 18
    FILEINFO = 19
    UP_CSF = 20


@unique
class POSTPROC(Enum):
    INJECT_DB = 24
    HISTORY = 25
    COLL_RES = 26
    RPT_RES = 27


@unique
class STATUS(Enum):
    SUCC = 0
    COND_SUCC = 1
    FAILED = 2
    FATAL = 3
    CANCEL = 4


class ERROR_RECOVER(object):

    def __init__(self, retry_sub_phase: str):
        self.retry_sub_phase = retry_sub_phase
        if os.path.exists(CONST_STR.RECOVER_POLICY.value):
            with open(CONST_STR.RECOVER_POLICY.value, 'r') as RECOVER_POLICY:
                self.recover_policy_data = json.load(RECOVER_POLICY)

    def retry_time(self):
        try:
            return self.recover_policy_data[self.retry_sub_phase]["RETRY"]
        except Exception:
            return 3  # default value if no such data

    def retry_timeout(self):
        try:
            return self.recover_policy_data[self.retry_sub_phase]["TIMEOUT"]
        except Exception:
            return 90  # default value if no such data


class SERVICE_RESTART(object):
    """

    """

    @staticmethod
    def scan_task_check():
        if os.path.exists(CONST_STR.XCALSCAN_FOLDER.value):
            if len(os.listdir(CONST_STR.XCALSCAN_FOLDER.value)) != 0:
                scan_task_list = os.listdir(CONST_STR.XCALSCAN_FOLDER.value)
                SERVICE_RESTART.scan_task_recover(scan_task_list)

    @staticmethod
    def scan_task_recover(scan_task_list: list):
        scan_fini_sp = PROC.ENGINE_MERGE.name
        for scan_task in scan_task_list:
            with open(scan_task, 'r') as scan_task_file:
                scan_task_record = scan_task_file.readlines()
            for ln, content in enumerate(scan_task_record):
                scan_record_content = re.search(r'(.*):fini', content)
                if scan_record_content:
                    scan_fini_sp = scan_record_content.group(1)


class POST_STATUS:
    """
    POST_STATUS() will do init, health check, fini and post status of main()
    the format of output message of post_status() is:
        "[FLOW] - $stage_enum: $status_enum ($arguments of main())"
    the format of output message of init() is:
        "[FLOW] - $stage_str: init"
    the format of output message of fini() is:
        "[FLOW] - $stage_str: fini"
    """
    """
    post_kafka_msg: post to Kafka to update the status of PROC
    scanTaskId: provide scan task ID
    status: PROC status
    dateTime: 13 bits timestamp
    """

    def __init__(self, scan_task_id: str, exec_parameters: str, fini_status: str, work_dir: str, if_cancel: bool,
                 output_files: str = "", error_code: int = 0, engine_scan_info: str = ""):
        self.scan_task_id = scan_task_id
        self.exec_parameters = exec_parameters
        self.fini_status = fini_status
        self.work_dir = work_dir
        self.if_cancel = if_cancel
        self.output_files = output_files
        self.engine_scan_info = engine_scan_info
        self.error_code = error_code

    def post_kafka_msg(self, phase: str):
        timestamp = int(round(time.time() * 1000))
        return {
            "source": phase,
            "scanTaskId": self.scan_task_id,
            "status": self.fini_status,
            "dateTime": timestamp
        }

    def scan_task_record(self, log_msg: str):
        record_folder = os.path.join(self.work_dir, CONST_STR.XCALSCAN_FOLDER.value)
        if not os.path.exists(record_folder):
            os.mkdir(record_folder)
        scan_task_record_file = "%s/%s" % (record_folder, self.scan_task_id)
        if not os.path.exists(scan_task_record_file):
            os.system(r"touch {}".format(scan_task_record_file))
        with open(scan_task_record_file, 'a') as file:
            file.write("%s\n" % log_msg)

    def scan_task_delete(self):
        record_folder = os.path.join(self.work_dir, CONST_STR.XCALSCAN_FOLDER.value)
        os.remove("%s/%s" % (record_folder, self.scan_task_id))

    def write_status_log(self, log_msg: str, time: datetime):
        gmt_format = '%Y-%m-%d %H:%M:%S'
        log_time = time.strftime(gmt_format)
        log_file = os.path.join(self.work_dir, CONST_STR.SCAN_TASK_LOG.value)
        with open(log_file, 'a') as log:
            log.write("%s, %s\n" % (log_time, log_msg))

    def status(self, stage: str, stage_enum: int):
        if self.engine_scan_info:
            log_msg = "%s, %s (%s) [outputs:%s], %s"\
                      % (stage, self.fini_status, self.exec_parameters, self.output_files, self.engine_scan_info)
        else:
            log_msg = "%s, %s (%s) [outputs:%s]" % (stage, self.fini_status, self.exec_parameters, self.output_files)
        self.write_status_log(log_msg, datetime.datetime.utcnow())
        self.scan_task_record(log_msg)

    # provide data for controller recover policy
    def health_query(self, stage: str):
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        health_msg = "Memory: total=%0.2fG used=%0.2fG free=%0.2fG, Disk: total=%0.2fG used=%0.2fG free=%0.2fG" % \
                     (self.byte_to_gb(memory.total),
                      self.byte_to_gb(memory.used),
                      self.byte_to_gb(memory.free),
                      self.byte_to_gb(disk.total),
                      self.byte_to_gb(disk.used),
                      self.byte_to_gb(disk.free))
        log_msg = "%s, %s" % (stage, health_msg)
        self.write_status_log(log_msg, datetime.datetime.utcnow())
        self.scan_task_record(log_msg)

    @staticmethod
    def byte_to_gb(value):
        return value / 1024 / 1024 / 1024

    def init(self, stage: str, stage_enum: int, init_time: datetime, extra_message: str = ""):
        log_msg = "%s, init" % stage
        if extra_message:
            log_msg += (",%s" % extra_message)
        self.write_status_log(log_msg, time=init_time)
        self.health_query(stage)
        self.scan_task_record(log_msg)

    def fini(self, stage: str, stage_enum: int, init_time: datetime):
        fini_time = datetime.datetime.utcnow()
        elapse_time = fini_time-init_time
        log_msg = "%s, fini(code:%s),Elapse Time(%s mSec)" %\
                  (stage, hex(self.error_code), elapse_time.total_seconds()*1000)
        self.status(stage, stage_enum)
        self.write_status_log(log_msg, time=fini_time)

    def retry(self, stage: str, retry_time: int):
        log_msg = "%s, retry - %s time" % (stage, retry_time)
        self.write_status_log(log_msg, datetime.datetime.utcnow())

    def cancel_scan_task(self):
        if self.if_cancel:
            log_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            log_file = os.path.join(self.work_dir, self.scan_task_id)
            log_file = os.path.join(log_file, CONST_STR.SCAN_TASK_LOG.value)
            log_msg = "%s" % STATUS.CANCEL.name
            with open(log_file, 'a') as log:
                log.write("%s, %s\n" % (log_time, log_msg))

    def if_cancel_scan_task(self):
        log_file = os.path.join(self.work_dir, CONST_STR.SCAN_TASK_LOG.value)
        if os.path.exists(log_file):
            with open(log_file, 'r') as log:
                log_msf = log.readlines()
            for msg in log_msf:
                if STATUS.CANCEL.name in msg:
                    self.write_status_log(STATUS.CANCEL.name, datetime.datetime.utcnow())
                    return True
        return False
