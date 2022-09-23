#  Copyright (C) 2019-2022 Xcalibyte (Shenzhen) Limited.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


import enum
import json
import logging
import os
import shutil
import subprocess
import time

import psutil

from common.CommonGlobals import Stage, Status, Percentage, VCS_DIFF_RESULT_FILE_NAME, PREPROCESS_FILE_NAME, \
    FILE_INFO_FILE_NAME, BASE_SCAN_PATH
from common.XcalLogger import XcalLogger, XcalLoggerExternalLinker
from scanTaskService.Config import push_gateway_url, registry, TaskErrorNo, \
    DESTINATION_DIR_SUFFIX, PREPROCESS_FILE_SUFFIX, scanFileSize, \
    scanFileLines, scanFileCount, SCAN_RUNNER_JOB_TOPIC, JAVA_SCAN_OBJECT_FILE_DIR, \
    JAVA_SCAN_RUNTIME_LOCAL_TEMP_FILE_NAME, REMOTE_RESULT_V_FILE_TEMP_NAME, TIMEOUT_DEFAULT_STAGE_SECONDS, \
    SCANNER_WORKER_TIMEOUT_LIST, COMPLETE_RATIO_FULL, SPOTBUGS_RESULT_V_FILE_TEMP_NAME, JAVA_RUNTIME_OBJECT_FILE_NAME, \
    JOB_QUEUE_NAME, SCAN_RESULT_CONVERTER
from scanTaskService.XcalExpirationWatch import ExpireHookType
from scanTaskService.components.AgentInfo import AgentInfoManagement, AgentInfoStatus
from scanTaskService.components.AgentInvoker import AgentInvoker
from scanTaskService.components.CachedFileStorage import CachedFileStorage
from scanTaskService.components.DiffService import DiffService
from scanTaskService.components.FileService import RemoteFileService
# from scanTaskService.components.FlattenResultService import FlattenResultService
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator
from scanTaskService.components.JobInitiator import JobInitiator, JobTimeoutManager
from scanTaskService.components.PostProcessService import PostProcessService
from scanTaskService.components.XvsaBootstapper import XvsaEngineBootstrapper
from scanTaskService.util.FileUtility import get_files_size_and_line_number
from common.CompressionUtility import CompressionUtility
from common.ConfigObject import ConfigObject, UserConfigObject


# ScanEngineRunner, start scanning
# Report Defects(issues) to Java Web Api
from scanTaskService.util.Metrics import ScanMetrics
from common.XcalException import XcalException


class ScanStageObject(object):
    def __init__(self, stage_type: str, info: dict, start: int, complete: int, sync: int = 1, last_stage: bool = False, timeout: int = 1):
        """
        Generate a stage object to append to the pipeline
        :param stage_type: str
        :param info: {}
        :param start: starting ratio in Stage, max = 100
        :param complete: completing ratio in Stage, max = 100
        :param sync: Synchronous Job (complete immediately), this will lead to immediate going to next stage
        :param last_stage: whether this is the last scan stage
        :param timeout: Timeout for the stage, in minutes.
        """
        self.stage_type = stage_type
        self.info = info
        self.start = start
        self.complete = complete
        self.sync = sync
        self.last_stage = last_stage
        self.timeout_minutes = timeout
        self.timeout_seconds = timeout * 60

    def as_dict(self):
        return {"type": self.stage_type, "startRatio": self.start, "completeRatio": self.complete, "syncJob": self.sync,
                "last_stage": self.last_stage, "timeout_seconds": self.timeout_seconds}


"""
This pipeline is used to create a sequence of jobs need to be completed in the scan
Adding a new stage to this pipeline will add this job to be performed in scanning.
Each Job will have a 'type' field indicating its identity and work to be done.
To add a new job, simply follow:
1. add it to the following pipeline, 
2. add a service capable of conducting the work
3. add the handling logic (switch-case) routing to the ScanController,
4. (OPTIONAL) if needed to perform it on the Agent side, simply add the step to AgentInvoker.prepare_steps

Parameters:
1. info, extra info used when performing task
2. start, starting ratio to report to web-api,
3. complete, completing ratio to report to web-api when stage was finished
4. sync, 0 if it is asynchronously finishing (ScanController.commit_task_done will be invoked separately by the Service), 
         1 if the stage is just a simple step and invoked between its predecessor and successor
5. timeout of this task, in milliseconds. (TODO:)
"""


class ControllerType(enum.Enum):
    DEFAULT_ASYNC = 1
    SCAN_ENGINE = 2
    pass


class ScanServiceBusinessLogic(object):

    def __init__(self, logger: XcalLogger):
        self.parent_logger = logger

    def get_configs(self, raw_task_config: dict):
        ConfigObject.verify_config(raw_task_config)
        self.task_config = ConfigObject(raw_task_config)
        if isinstance(raw_task_config.get("configContent"), str):
            user_config = UserConfigObject(raw_task_config.get("configContent"))
            self.task_config = ConfigObject(self.task_config.merge_two_dicts(self.task_config.convert_to_dict(), user_config.convert_to_dict()))
        self.task_config.set("span", XcalLoggerExternalLinker.prepare_client_request_string("ScanServiceBusinessLogic", "get_configs", self.parent_logger))
        return self.task_config

    def initiate_scan_pipeline(self, task_config: ConfigObject):
        with XcalLogger("ScanServiceBusinessLogic",
                        "initiate_scan_pipeline",
                        parent=self.parent_logger) as log:
            log.trace("initiate_scan_pipeline", "starting pipeline creation for a scan, raw_data=%s" % (task_config.dumps()))
            pipeline = []

        # For C++/Java Projects
        # TODO: TIMEOUT should be added here, start and complete should be removed?
        # TUNE GUIDE : Refine start and complete ratio
        log.trace("initiate_scan_pipeline", "agent type: %s" % task_config.get("agentType"))
        if task_config.get("agentType") != 'offline_agent':
            pipeline.append(ScanStageObject(stage_type="prescan",                 start=5,  complete=80,  sync=0, last_stage=False, timeout=60,  info={}).as_dict())
        if task_config.get("lang") is not None and task_config.get("lang") == "java":
            # Java Scanning Pipeline
            pipeline.append(ScanStageObject(stage_type="getPrescanObject",        start=81, complete=90,  sync=1, last_stage=False, timeout=30,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="getJavaRuntimeObject",    start=91, complete=100, sync=1, last_stage=False, timeout=30,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="xvsa",                    start=5,  complete=80,  sync=0, last_stage=False, timeout=240, info={}).as_dict())
            # pipeline.append(ScanStageObject(stage_type="flattenResult",           start=85, complete=100, sync=1, last_stage=False, timeout=20,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="packageResult",           start=5,  complete=50,  sync=1, last_stage=False, timeout=20,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="diff",                    start=5,  complete=100, sync=1, last_stage=False, timeout=20,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="reportResult",            start=5,  complete=50,  sync=1, last_stage=False, timeout=240, info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="remoteScanResult",        start=70, complete=100, sync=1, last_stage=True,  timeout=20,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="postProcess",             start=5,  complete=100, sync=1, last_stage=False, timeout=20,  info={}).as_dict())
        else:
            # C/C++ Scanning Pipeline
            pipeline.append(ScanStageObject(stage_type="getPrescanObject",        start=81, complete=100, sync=1, last_stage=False, timeout=30,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="xvsa",                    start=5,  complete=90,  sync=0, last_stage=False, timeout=240, info={}).as_dict())
            # pipeline.append(ScanStageObject(stage_type="flattenResult",           start=85, complete=100, sync=1, last_stage=False, timeout=20,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="oclint",                  start=95, complete=100, sync=1, last_stage=False, timeout=10,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="packageResult",           start=5,  complete=50,  sync=1, last_stage=False, timeout=20,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="diff",                    start=5,  complete=100, sync=1, last_stage=False, timeout=20,  info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="reportResult",            start=5,  complete=100, sync=1, last_stage=True,  timeout=240, info={}).as_dict())
            pipeline.append(ScanStageObject(stage_type="uploadDiagnosticInfo",    start=5,  complete=100, sync=1, last_stage=False, timeout=10,  info={}).as_dict())

        task_config.set("pipeline", pipeline)
        task_config.set("pipelineOffset", "0")
        task_config.set("target", "internal")
        task_config.set("uploadResultSuccessNumber", "0")

        log.trace("initiate_scan_pipeline", "submitting pipeline to JobInitiator, waiting to be processed. " + str(task_config.convert_to_dict()))

        JobInitiator(log).initiate_job_flow(SCAN_RUNNER_JOB_TOPIC, task_config.convert_to_dict(), ExpireHookType.EXPIRE_IGNORE)


class ScanController:
    def __init__(self, logger: XcalLogger, type:ControllerType = ControllerType.DEFAULT_ASYNC):
        """
        Creating a controller, which is thread safe
        :param logger:
        """
        self.parent_logger = logger
        self.execution = {"type": type}

    def get_pipeline_stage(self, config_info: ConfigObject):
        with XcalLogger("ScanController", "get_pipeline_stage", parent=self.parent_logger) as log:
            log.debug("get_pipeline_stage", "config_info: %s" % config_info)
            if config_info.get('pipeline') is None or config_info.get('pipelineOffset') is None:
                raise XcalException("XcalServices", "get_pipeline_stage", "no pipeline to work on",
                                    TaskErrorNo.E_NO_PIPELINE)
            pipeline = config_info.get("pipeline")
            pipeline_offset = int(config_info.get('pipelineOffset'))
            if pipeline_offset >= len(pipeline):
                raise XcalException("XcalServices", "get_pipeline_stage",
                                    "pipelineOffset = %d, exceed total length = %d" % (pipeline_offset, len(pipeline)),
                                    TaskErrorNo.E_PIPELINE_OFFSET)

            stage = pipeline[pipeline_offset]
            if stage is None:
                stage = {"type": "Unknown"}
            return stage

    @staticmethod
    def determine_status_based_on_upload_results(task_config: ConfigObject):
        """
        Determine scan status based on upload result situation.
        This method should be used when pipeline stage is the last stage
        :param task_config:
        :return:
        """
        if int(task_config.get("uploadResultSuccessNumber")) != 0:
            scan_status = Status.COMPLETED
        else:
            scan_status = Status.FAILED

        return scan_status

    def get_scan_stage_and_status(self, stage, task_config: ConfigObject):
        """
        get the scan stage and status
        :param stage: pipeline stage
        :param task_config:
        :return:
        """
        scan_stage = None
        scan_status = Status.PROCESSING
        if stage.get("type") == "getPrescanObject":
            scan_stage = Stage.SCAN_QUEUE_XVSA
        elif stage.get("type") == "xvsa":
            if self.execution == ControllerType.SCAN_ENGINE:
                scan_stage = Stage.SCAN_QUEUE_IMPORT_RESULT
        elif stage.get("last_stage"):
            scan_stage = Stage.SCAN_COMPLETE
            scan_status = ScanController.determine_status_based_on_upload_results(task_config)

        return scan_stage, scan_status

    def process_internal_job(self, data_obj: dict, no_timeout: bool = False):
        """
        Executing the steps defined in the scan pipeline.

        :param data_obj:  {"pipeline": ... , "pipelineOffset": <Stage to be done, starting from 0>, "scanTaskId":... }
        :param no_timeout:
        :return:
        """
        one = ConfigObject(data_obj)
        local_parent_logger = self.parent_logger
        if one.get("span") is not None:
            local_parent_logger = XcalLoggerExternalLinker.prepare_server_span_scope_from_string("XcalServices", "process_internal_job", one.get("span", "{}"))

        with XcalLogger("ScanController", "process_internal_job", parent=local_parent_logger) as log:
            # log statistics info
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            log.trace('process_internal_job',
                      'Memory: total=%0.2fG, used=%0.2fG, free=%0.2fG Disk: total=%0.2fG, used=%0.2fG, free=%0.2fG' % (
                          memory.total / 1024 / 1024 / 1024,
                          memory.used / 1024 / 1024 / 1024,
                          memory.free / 1024 / 1024 / 1024,
                          disk.total / 1024 / 1024 / 1024,
                          disk.used / 1024 / 1024 / 1024,
                          disk.free / 1024 / 1024 / 1024
                      ))

            log.trace("process_internal_job", "processing %s ...." % str(data_obj))
            scan_id = one.get("scanTaskId")
            comms = XcalInternalCommunicator(log, one)
            stage = {"type": "Unknown"}

            try:
                stage = self.get_pipeline_stage(one)
                log.set_tag("jaeger_tag", stage.get("type"))
                log.trace("stage %s starting ..." % (stage.get("type")), ())

                # Setting up job timeout hook
                if not no_timeout and (self.execution.get("type") == ControllerType.DEFAULT_ASYNC):
                    timeout_manager = JobTimeoutManager(log)
                    config_dict = one.convert_to_dict()

                    timeout = int(stage.get("timeout_seconds", TIMEOUT_DEFAULT_STAGE_SECONDS))
                    timeout = timeout_manager.override_timeout_from_user_config(config_dict, timeout, stage.get("type"))
                    timeout_manager.start_timeout(SCANNER_WORKER_TIMEOUT_LIST, config_dict, timeout_seconds=timeout)
                    log.trace("stage %s starting, timeout = %d ..." % (stage.get("type"), timeout), ())
                    one.set("timeoutMan", config_dict.get("timeoutMan", {}))

                if stage.get("type") == "prescan":
                    ps = PrescanService(log, one, stage)
                    ps.publish_job()
                elif stage.get("type") == "getPrescanObject":
                    pofr = PrescanObjectFileRetriever(log, one, stage)
                    pofr.execute()
                elif stage.get("type") == "xvsa":
                    # Kick off scan
                    XvsaEngineRunnerService(log, one, stage, execution=self.execution).execute()
                elif stage.get("type") == "oclint":
                    # Run OCLINT
                    OClintScanEngineService(log, one, stage).execute()
                # elif stage.get("type") == "flattenResult":
                    # Flatten Results from multiple module v files
                    # FlattenResultService(log, one, stage).flatten_scan_result()
                elif stage.get("type") == "packageResult":
                    # package scan result to reduce the scan result size and transfer cost
                    PackageScanResultService(log, one).execute()
                elif stage.get("type") == "getJavaRuntimeObject":
                    # Run JavaRuntime Get Object
                    RuntimeObjectFetchingService(log, one, stage).get_runtime_library()
                elif stage.get("type") == "reportResult":
                    # upload scan results
                    ScanReporterService(log, one, stage).execute()
                elif stage.get("type") == "diff":
                    # diff scan result
                    XcalDiffService(log, one, stage).do_diff()
                elif stage.get("type") == "postProcess":
                    PostProcessService(log, one).post_process()
                elif stage.get("type") == "uploadProgress":
                    ProgressReporterService(log, one, stage).execute()
                elif stage.get("type") == "remoteScanResult":
                    RemoteResultUploader(log, one, stage).execute()
                elif stage.get("type") == "uploadDiagnosticInfo":
                    UploadDiagnosticInfoService(log, one).execute()
                else:
                    raise XcalException("ScanController", "process_internal_job",
                                        "pipeline stage type %s not recognizable" % str(stage.get("type")),
                                        TaskErrorNo.E_STAGE_NOT_RECOGNIZE)

                scan_stage, scan_status = self.get_scan_stage_and_status(stage, one)

                log.trace("process_internal_job", "pipeline stage %s completed, scan_stage: %s, scan_status: %s" % (stage.get("type"), scan_stage, scan_status))

                if stage.get("syncJob") == 1:
                    if scan_stage:
                        message = "update stage to %s" % scan_stage
                        percentage = Percentage.START
                    # The status of the last stage failed means all import result operation is failed
                    if scan_stage == Stage.SCAN_COMPLETE and scan_status == Status.FAILED:
                        scan_stage = Stage.IMPORT_RESULT
                        percentage = Percentage.END
                        comms.upload_progress(data_obj.get("scanTaskId"), scan_stage, scan_status, percentage, "all import result is failed",
                                              TaskErrorNo.E_IMPORT_RESULT_ALL_FAILED)
                    elif scan_stage:
                        if scan_stage == Stage.SCAN_COMPLETE:
                            comms.upload_progress(data_obj.get("scanTaskId"), scan_stage, scan_status, percentage, message)
                        else:
                            comms.upload_progress(data_obj.get("scanTaskId"), scan_stage, scan_status, percentage, message)
                    self.commit_task_done(one)

            except XcalException as err:
                logging.exception(err)

                stage_name = str(stage.get("type", "Unknown stage"))

                log.error("ScanController", "process_internal_job", ("exception occurred", err))
                log.error("ScanController", "process_internal_job", one.dumps())

                if comms is not None:
                    message = "Scan Failed in stage %s, message: %s" % (stage_name, err.message)
                    comms.upload_progress(data_obj.get("scanTaskId"), Stage.SCANNING, Status.FAILED, Percentage.END, message, err.err_code)

            except Exception as err:
                logging.exception(err)
                log.trace("executing stage %s" % str(stage), "task id = %s" % data_obj.get("scanTaskId"))
                log.error("ScanController", "process_internal_job", ("unexpected exception occurred", str(err)))

                if comms is not None:
                    message = "scan pipeline failed due to unexpected exception: %s" % str(err)
                    comms.upload_progress(scan_id, Stage.SCANNING, Status.FAILED, Percentage.END, message, TaskErrorNo.E_SRV_SCAN_UNKNOWN_ERROR)

            ScanMetrics.push_to_gateway(push_gateway_url, job='scanTaskService', reg=registry)
            log.finish()

    def commit_task_done(self, task_config: ConfigObject):
        # If no-next step, stop here.
        # Otherwise, continue to Kafka
        pipeline_offset = int(task_config.get('pipelineOffset'))
        pipeline = task_config.get("pipeline")

        with XcalLogger("ScanController", "commit_task_done", parent=self.parent_logger) as log:
            # Clearing the job timeout hook
            if len(task_config.get("timeoutMan", [])) > 0:
                timeout_manager = JobTimeoutManager(log)
                config_dict = task_config.convert_to_dict()
                if timeout_manager.is_expired(config_dict):
                    log.trace("commit_task_done", "the job has already expired so will not continue to work")
                    raise XcalException("ScanController", "commit_task_done",
                                        "the job has already expired so will not continue to work",
                                        TaskErrorNo.E_JOB_EXPIRE)
                else:
                    timeout_manager.complete_task(config_dict)

            if 0 <= pipeline_offset < (len(pipeline) - 1):
                pipeline_offset += 1
                task_config.set("pipelineOffset", str(pipeline_offset))
                # Will proceed according to the pipeline table above
                # The following line will submit task to Kafka and eventually get back from ScanServiceWorker to process_internal_job above
                JobInitiator(log) \
                    .initiate_job_flow(SCAN_RUNNER_JOB_TOPIC, task_config.convert_to_dict(), ExpireHookType.EXPIRE_IGNORE)
            else:
                log.trace("ScanController", "commit_task_done, the pipeline (len = %d) was completed with offset = %d done" %
                                       (len(pipeline), pipeline_offset))


class ProgressReporterService(object):
    def __init__(self, logger: XcalLogger, task_config: ConfigObject, stage):
        self.task_config = task_config
        self.logger = XcalLogger("ProgressReporterService", "__init__", parent=logger)

    def execute(self):
        communicator = XcalInternalCommunicator(self.logger, self.task_config)

        scan_id = self.task_config.get("scanTaskId")
        message = self.task_config.get("message")

        self.logger.trace("execute", "scan_id: %s, stage: %s, status: %s, percentage: %s, message: %s" % (
            scan_id, self.task_config.get("stage"), self.task_config.get("status"), self.task_config.get("progress"), message))

        try:
            stage = Stage(self.task_config.get("stage"))
            status = Status(self.task_config.get("status"))
            percentage = Percentage(self.task_config.get("progress"))
            error_code = TaskErrorNo(self.task_config.get("errorInfo"))
        except ValueError as e:
            logging.exception(e)
            stage = Stage.SCANNING
            status = Status.FAILED
            percentage = Percentage.END
            message = str(self.task_config.get("extraInfo", ""))
            error_code = TaskErrorNo.E_COMMON_INVALID_VALUE
        else:
            if error_code in [TaskErrorNo.E_NO_AGENT_CONN_TIMEOUT, TaskErrorNo.E_AGENT_IS_BUSY,
                              TaskErrorNo.E_NO_ACTIVE_AGENT_FOR_THIS_JOB, TaskErrorNo.E_COMMON_UNKNOWN_ERROR]:
                self.logger.warn("execute", "job expire due to no agent do it or agent is busy or unknown error")
                stage = Stage.AGENT_START
                status = Status.FAILED
                percentage = Percentage.END
                message = str(self.task_config.get("extraInfo", ""))

            elif error_code == TaskErrorNo.SUCCESS:
                if message is None:
                    self.logger.warn("execute", "message information is missing")
                    message = "report status"
                error_code = None
            else:
                self.logger.trace("execute", "error occurs in %s" % str(self.task_config.get("origin", "agent")))

        communicator.upload_progress(scan_id, stage, status, percentage, message=message, error_code = error_code)


class PrescanService(object):
    def __init__(self, logger: XcalLogger, task_config:ConfigObject, stage:dict):
        self.logger = logger
        self.comms = XcalInternalCommunicator(self.logger, task_config)

        # Prescan Variables -----------------------------
        scan_id = task_config.get('scanTaskId')
        src_location = task_config.get('preprocessPath')
        self.stage = stage
        self.task_config = task_config
        self.scan_id = scan_id
        self.src_location = src_location
        self.path_list = self.src_location.split(self.scan_id, 1)
        self.source_code_root_path = self.path_list[0]

    def publish_job(self):
        """
        send job to agent queue
        :return: None
        """
        with XcalLogger("PrescanService", "publish_job", parent = self.logger) as agent_log:

            job_queue_name = self.task_config.get('jobQueueName', JOB_QUEUE_NAME)
            agent_info_status = AgentInfoManagement.get_agent_info_status(job_queue_name)

            if agent_info_status == AgentInfoStatus.NO_AGENT:
                agent_log.warn("publish_job", "no active agent")
                self.comms.upload_progress(self.scan_id, Stage.PRE_SCAN_QUEUE, Status.TERMINATED,
                                           Percentage.END,
                                           "no active agent", TaskErrorNo.E_NO_ACTIVE_AGENT_FOR_THIS_JOB)
            elif agent_info_status == AgentInfoStatus.JOB_QUEUE_NAME_NOT_SUPPORT:
                agent_log.warn("publish_job", "no active agent for this job")
                self.comms.upload_progress(self.scan_id, Stage.PRE_SCAN_QUEUE, Status.TERMINATED,
                                           Percentage.END,
                                           "no active agent for this job", TaskErrorNo.E_NO_ACTIVE_AGENT_FOR_THIS_JOB)
            else:
                self.comms.upload_progress(self.scan_id, Stage.PREPARE_WORKER_PIPELINE, Status.PROCESSING,
                                           Percentage.START,
                                           "prepare agent worker job pipeline")

                agent_invoke = AgentInvoker(agent_log)
                job_steps = agent_invoke.prepare_steps(self.src_location, self.task_config)

                self.comms.upload_progress(self.scan_id, Stage.PRE_SCAN_QUEUE, Status.PROCESSING,
                                           Percentage.START,
                                           "publish job steps and scan task pipeline to mq")
                agent_invoke.invoke_agent_via_queue(job_steps, self.task_config)

    def execute(self):
        self.publish_job()


class PrescanObjectFileRetriever(object):
    def __init__(self, logger:XcalLogger, task_config:ConfigObject, stage:dict):
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.scan_work_dir = os.path.join(BASE_SCAN_PATH, self.scan_id)
        self.task_info = task_config
        self.stage = stage
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def execute(self):
        """
        Fetch the artifact in tarball and untar
        :return:
        """
        with XcalLogger("PrescanObjectFileRetriever", "execute", parent= self.logger) as log:
            # Receive preprocess result in tar and extract
            i_file_tar_archive_temp_filename = os.path.join(self.scan_work_dir, PREPROCESS_FILE_NAME)
            i_file_archive_file_id = AgentInvoker.extract_remote_file_id(self.task_info, PREPROCESS_FILE_NAME)

            if i_file_archive_file_id is None:
                raise XcalException("PrescanObjectFileRetriever", "execute", "No agent resolved file id found",
                                    TaskErrorNo.E_SRV_GETPREPROC_NO_PRESCAN_RESULT)

            scan_preprocess_file_dir_name = self.scan_id + DESTINATION_DIR_SUFFIX
            log.trace("Fetching tarball from file service : ID[%s] => %s" % (i_file_archive_file_id, i_file_tar_archive_temp_filename), "")

            self.comms.upload_progress(self.scan_id, Stage.FETCH_PRE_PROCESS_INFO, Status.PROCESSING, Percentage.START,
                                       "begin to fetch preprocess result package")

            RemoteFileService(self.task_info, log).fetch_file_with_token(i_file_archive_file_id,
                                                                         i_file_tar_archive_temp_filename,
                                                                         self.task_info)
            log.trace("Decompressing : %s => %s" % (
                i_file_tar_archive_temp_filename, os.path.join(self.scan_work_dir, scan_preprocess_file_dir_name)), "")
            CompressionUtility.extract_file(log, i_file_tar_archive_temp_filename, os.path.join(self.scan_work_dir, scan_preprocess_file_dir_name), remove=False)

            self.collect_monitor_info(log, scan_preprocess_file_dir_name)

            # Receive File Info -----------------------------
            file_info_file_id = AgentInvoker.extract_remote_file_id(self.task_info, FILE_INFO_FILE_NAME)
            json_file_local_temp_name = os.path.join(self.scan_work_dir, FILE_INFO_FILE_NAME)
            log.trace("Fetching fileinfo file from server : ID[%s] => %s" % (
                file_info_file_id, json_file_local_temp_name), "")

            self.comms.upload_progress(self.scan_id, Stage.FETCH_PRE_PROCESS_INFO, Status.PROCESSING, Percentage.MIDDLE,
                                       "begin to fetch file info file")

            RemoteFileService(self.task_info, log).fetch_file_with_token(file_info_file_id, json_file_local_temp_name,
                                                                         self.task_info)

    def collect_monitor_info(self, parent_log:XcalLogger, scan_preprocess_file_dir_name:str):
        """
        Collect file count / file size ... to send to Monitor service
        :param parent_log:
        :param scan_preprocess_file_dir_name:
        :return:
        """
        with XcalLogger("PrescanObjectFileRetriever", "collect_monitor_info", parent=parent_log) as log:
            # Prometheus Collection -------------------------
            try:
                size, lines, file_count = get_files_size_and_line_number(
                    os.path.join(self.scan_work_dir, scan_preprocess_file_dir_name), PREPROCESS_FILE_SUFFIX)
                log.info("collect_monitor_info", " size = %d, lines = %d, file_count = %d" % (size, lines, file_count))
                scanFileSize.set(size)
                scanFileLines.set(lines)
                scanFileCount.set(file_count)
            except Exception as err:
                logging.exception(err)
                log.error("PrescanObjectFileRetriever", "collect_monitor_info", "metrics collection reported exception")


class RuntimeObjectFetchingService(object):
    def __init__(self, logger:XcalLogger, task_config:ConfigObject, stage:dict):
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.scan_path = os.path.join(BASE_SCAN_PATH, self.scan_id)
        self.task_config = task_config
        self.stage = stage
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def get_runtime_library(self):
        """
        Get rt.o or rt.jar by file-id
        :return:
        """
        # 1. Get Runtime library file (file-id)
        # 2. Download and decompress file to /share/scan/{scan_id}
        # 3. place the rt.o or rt.jar files to the XVSA scan extra obj list
        self.comms.upload_progress(self.scan_id, Stage.FETCH_PRE_PROCESS_INFO, Status.PROCESSING, Percentage.MIDDLE,
                                   "start fetch runtime library file")

        cache = CachedFileStorage(self.logger, self.task_config)
        checksum = self.task_config.get("runtimeLibraryChecksum")
        runtime_cache_setting_value = cache.check_storage_exists(checksum)

        if runtime_cache_setting_value is None:
            self.logger.warn("get_runtime_library", "no caching file related to checksum %s found" % checksum)
        else:
            artifact_file_id = runtime_cache_setting_value.get("artifactFileId")
            file_id = runtime_cache_setting_value.get("fileId")
            if artifact_file_id is None and file_id is None:
                self.logger.warn("get_runtime_library", "cannot find rt.o or rt.jar!")

            local_runtime_file_package = os.path.join(self.scan_path, JAVA_SCAN_RUNTIME_LOCAL_TEMP_FILE_NAME)
            if artifact_file_id is not None:
                self.logger.trace("get_runtime_library", "start fetch rt.o")
                RemoteFileService(self.task_config, self.logger).fetch_file_with_token(artifact_file_id, local_runtime_file_package, self.task_config)
                dest_path = self.scan_path
            elif file_id is not None:
                self.logger.info("get_runtime_library", "start fetch rt.tgz")
                RemoteFileService(self.task_config, self.logger).fetch_file_with_token(file_id, local_runtime_file_package, self.task_config)
                dest_path = os.path.join(self.scan_path, JAVA_SCAN_OBJECT_FILE_DIR)

            CompressionUtility.extract_file(self.logger, local_runtime_file_package, dest_path, remove = True)

        self.comms.upload_progress(self.scan_id, Stage.FETCH_PRE_PROCESS_INFO, Status.PROCESSING, Percentage.END, "fetch runtime library file complete")


class XvsaEngineRunnerService(object):
    def __init__(self, logger: XcalLogger, task_config, stage: dict, execution:dict):
        """
        Execution is the working context from controller, params from its container (i.e. ScanEngineServiceJobListener)
        :param logger:
        :param task_config:
        :param stage:
        :param execution:
        """
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.task_config = task_config
        self.stage = stage
        self.execution = execution
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def publish_job(self):
        """
        send job to scan engine queue (currently is xvsa)
        :return:
        """
        with XcalLogger(str(XvsaEngineRunnerService.__name__), str(XvsaEngineRunnerService.publish_job.__name__), parent=self.logger) as log:
            self.comms.upload_progress(self.scan_id, Stage.SCAN_ENGINE_QUEUE, Status.PROCESSING, Percentage.START, "publish job to scan engine queue")
            XvsaEngineBootstrapper(log).invoke_xvsa_via_queue(self.task_config.convert_to_dict())

    def perform_sync_scan(self):
        with XcalLogger(str(XvsaEngineRunnerService.__name__), str(XvsaEngineRunnerService.execute.__name__), parent=self.logger) as log:
            self.stage["syncJob"] = 1
            self.comms.upload_progress(self.scan_id, Stage.SCANNING, Status.PROCESSING,
                                       Percentage.START, "start scanning")
            # Start off XVSA scan -------------------------
            XvsaEngineBootstrapper(log).execute_scan(self.task_config)
            XvsaEngineBootstrapper(log).post_scan_cleanup(self.task_config)

            if int(self.stage.get("completeRatio")) == COMPLETE_RATIO_FULL:
                self.comms.upload_progress(self.scan_id, Stage.SCANNING, Status.PROCESSING, Percentage.END, "xvsa scanning done, all scan completed")
            else:
                # This is only used in case of oclint pending scan task, thus xvsa does not fully occupy the scan stage.
                self.comms.upload_progress(self.scan_id, Stage.SCANNING, Status.PROCESSING,
                                           Percentage.MIDDLE, "xvsa scanning done, continuing")

    def execute(self):
        """
        Start Scanning (currently is xvsa)
        :return:
        """
        if self.execution.get("type", ControllerType.DEFAULT_ASYNC) == ControllerType.DEFAULT_ASYNC:
            self.publish_job()
        elif self.execution.get("type", ControllerType.DEFAULT_ASYNC) == ControllerType.SCAN_ENGINE:
            self.perform_sync_scan()
        else:
            raise XcalException("XvsaEngineRunnerService", "execute", "Cannot determine execution type, not DEFAULT_ASYNC, nor SCAN_ENGINE",
                                TaskErrorNo.E_SRV_XVSA_UNKNOWN_EXECTUTE_TYPE)


class OClintScanEngineService(object):
    def __init__(self, logger:XcalLogger, task_config:ConfigObject, stage:dict):
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def execute(self):
        pass


class CachedFileStorageService(object):
    def __init__(self, logger:XcalLogger, task_config:ConfigObject, stage:dict):
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.comms = XcalInternalCommunicator(self.logger, task_config)


class XcalDiffService(object):

    def __init__(self, logger: XcalLogger, task_config, stage: dict):
        self.logger = logger
        self.task_config = task_config
        self.stage = stage

        self.scan_id = self.task_config.get('scanTaskId')
        self.scan_work_dir = os.path.join(BASE_SCAN_PATH, self.scan_id)
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def get_vcs_diff_file(self):
        vcs_diff_file_id = AgentInvoker.extract_remote_file_id(self.task_config, VCS_DIFF_RESULT_FILE_NAME)
        vcs_diff_file_path = os.path.join(self.scan_work_dir, VCS_DIFF_RESULT_FILE_NAME)
        RemoteFileService(self.task_config, self.logger).fetch_file_with_token(vcs_diff_file_id, vcs_diff_file_path, self.task_config)
        return vcs_diff_file_path

    def prepare_and_diff(self, baseline_scan_task_id, log: XcalLogger):
        diff_file_path, ntxt_file_path, ltxt_file_path, etxt_file_path, ftxt_file_path = None, None, None, None, None
        if baseline_scan_task_id is not None:
            diff_file_path = self.get_vcs_diff_file()
            log.trace("prepare_and_diff", "diff_file_path: %s" % diff_file_path)
            if not os.path.exists(diff_file_path):
                raise XcalException('XcalDiffService', 'prepare_and_diff', 'diff_file_path not exists', TaskErrorNo.E_SRV_GIT_DIFF_NOT_EXISTS)
            ntxt_file_path = os.path.join(BASE_SCAN_PATH, baseline_scan_task_id, 'xvsa-xfa-dummy.ntxt')
            log.trace("prepare_and_diff", "ntxt_file_path: %s" % ntxt_file_path)
            if not os.path.exists(ntxt_file_path):
                raise XcalException('XcalDiffService', 'prepare_and_diff', 'ntxt_file_path not exists', TaskErrorNo.E_SRV_BASELINE_VTXT_NOT_EXISTS)
            ltxt_file_path = os.path.join(BASE_SCAN_PATH, baseline_scan_task_id, 'xvsa-xfa-dummy.ltxt')
            log.trace("prepare_and_diff", "ltxt_file_path: %s" % ltxt_file_path)
            if not os.path.exists(ltxt_file_path):
                raise XcalException('XcalDiffService', 'prepare_and_diff', 'ltxt_file_path not exists', TaskErrorNo.E_SRV_BASELINE_VTXT_NOT_EXISTS)
            etxt_file_path = os.path.join(BASE_SCAN_PATH, baseline_scan_task_id, 'xvsa-xfa-dummy.etxt')
            log.trace("prepare_and_diff", "etxt_file_path: %s" % etxt_file_path)
            if not os.path.exists(etxt_file_path):
                raise XcalException('XcalDiffService', 'prepare_and_diff', 'etxt_file_path not exists', TaskErrorNo.E_SRV_BASELINE_VTXT_NOT_EXISTS)
            ftxt_file_path = os.path.join(BASE_SCAN_PATH, baseline_scan_task_id, 'xvsa-xfa-dummy.ftxt')
            log.trace("prepare_and_diff", "ftxt_file_path: %s" % ftxt_file_path)
            if not os.path.exists(ftxt_file_path):
                raise XcalException('XcalDiffService', 'prepare_and_diff', 'ftxt_file_path not exists', TaskErrorNo.E_SRV_BASELINE_VTXT_NOT_EXISTS)
        try:
            DiffService(self.logger, diff_file_path, ntxt_file_path, ltxt_file_path, etxt_file_path, ftxt_file_path, self.scan_work_dir).diff_scan_result()
        except XcalException as e:
            log.error(e.service, e.operation, e.message)
            self.comms.upload_progress(self.logger, diff_file_path, ntxt_file_path, ltxt_file_path, etxt_file_path, ftxt_file_path, Status.FAILED, Percentage.END, e.message, e.err_code)
        except Exception as e:
            logging.exception(e)
            log.error("XcalDiffService", "gen_git_diff_line_map", "unexpected exception: %s" % str(e))
            self.comms.upload_progress(self.logger, diff_file_path, ntxt_file_path, ltxt_file_path, etxt_file_path, ftxt_file_path, Status.FAILED, Percentage.END, e.message, e.err_code)

    def do_diff(self):
        with XcalLogger(str(XcalDiffService.__name__), str(XcalDiffService.do_diff.__name__), parent=self.logger) as log:
            log.trace("do_diff", "begin to do diff, scan task id: %s" % self.scan_id)
            self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT_DIFF, Status.PROCESSING, Percentage.START, "begin to do diff")

            try:
                # do diff condition2: baseline commit id has corresponding scan task id
                # call search api get baseline scan task id by project id and baseline commit id
                scan_task_info = self.comms.search_scan_task()
                if scan_task_info is None:
                    raise XcalException('XcalDiffService', 'do_diff', 'invalid scan_task_info', TaskErrorNo.E_SRV_GET_SCAN_TASK_INFO_FAILED)
                log.debug("do_diff", "scan task info: %s" % scan_task_info.json())
                baseline_scan_task_id = None
                if len(scan_task_info.json().get("content")) > 0:
                    baseline_scan_task_id = scan_task_info.json().get("content")[0].get("id")
                self.prepare_and_diff(baseline_scan_task_id, log)
                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT_DIFF, Status.PROCESSING, Percentage.END, 'diff and import diff result complete')
            except XcalException as e:
                log.error(e.service, e.operation, e.message)
                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT_DIFF, Status.FAILED, Percentage.END, e.message, e.err_code)
            except Exception as e:
                logging.exception(e)
                log.error("XcalDiffService", "do_diff", "unexpected exception: %s" % str(e))
                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT_DIFF, Status.FAILED, Percentage.END, "diff and import diff result failed, unexpected exception occurs", -1)


class ScanReporterService(object):

    def __init__(self, logger: XcalLogger, task_config, stage: dict):
        self.logger = logger
        self.task_config = task_config
        self.stage = stage

        self.scan_id = self.task_config.get('scanTaskId')
        self.scan_work_dir = os.path.join(BASE_SCAN_PATH, self.scan_id)
        self.host_path = self.task_config.get('sourceCodePath')
        self.target_path = self.task_config.get('preprocessPath')
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def execute(self):
        """
        Upload the defects to Java Web Api.
        :return: the number of upload scan results successful
        """
        with XcalLogger(str(ScanReporterService.__name__), str(ScanReporterService.execute.__name__), parent=self.logger) as log:
            try:
                if not os.path.exists(SCAN_RESULT_CONVERTER):
                    raise XcalException('ScanReporterService', 'execute', '%s not exists' % SCAN_RESULT_CONVERTER, TaskErrorNo.E_SRV_V2CSF_NOT_EXISTS)

                log.trace('execute', 'starting convert scan result')

                ntxt_file_path = os.path.join(self.scan_work_dir, 'xvsa-xfa-dummy.ntxt')
                log.trace("execute", "ntxt_file_path: %s" % ntxt_file_path)
                if not os.path.exists(ntxt_file_path):
                    raise XcalException('ScanReporterService', 'execute', 'ntxt_file_path not exists', TaskErrorNo.E_SRV_CURRENT_VTXT_NOT_EXISTS)
                ltxt_file_path = os.path.join(self.scan_work_dir, 'xvsa-xfa-dummy.ltxt')
                log.trace("execute", "ltxt_file_path: %s" % ltxt_file_path)
                if not os.path.exists(ltxt_file_path):
                    raise XcalException('ScanReporterService', 'execute', 'ltxt_file_path not exists', TaskErrorNo.E_SRV_CURRENT_VTXT_NOT_EXISTS)
                etxt_file_path = os.path.join(self.scan_work_dir, 'xvsa-xfa-dummy.etxt')
                log.trace("execute", "etxt_file_path: %s" % etxt_file_path)
                if not os.path.exists(etxt_file_path):
                    raise XcalException('ScanReporterService', 'execute', 'etxt_file_path not exists', TaskErrorNo.E_SRV_CURRENT_VTXT_NOT_EXISTS)
                ftxt_file_path = os.path.join(self.scan_work_dir, 'xvsa-xfa-dummy.ftxt')
                log.trace("execute", "ftxt_file_path: %s" % ftxt_file_path)
                if not os.path.exists(ftxt_file_path):
                    raise XcalException('ScanReporterService', 'execute', 'ftxt_file_path not exists', TaskErrorNo.E_SRV_CURRENT_VTXT_NOT_EXISTS)

                params = [SCAN_RESULT_CONVERTER]
                if self.host_path is not None and len(self.host_path) > 0:
                    params.extend(['-h', self.host_path])
                if self.target_path is not None and len(self.target_path) > 0:
                    params.extend(['-t', self.target_path])

                params.extend(['-n', ntxt_file_path])
                params.extend(['-l', ltxt_file_path])
                params.extend(['-e', etxt_file_path])
                params.extend(['-f', ftxt_file_path])
                params.extend(['-d', '-p', os.path.join(self.scan_work_dir, '.scan_log')])

                log.trace("execute", json.dumps(params))
                try:
                    st = time.time()
                    p = subprocess.run(params, stdout=subprocess.PIPE, timeout=5400)
                    et = time.time()
                    log.trace("execute", 'execute %s time: %f' % (SCAN_RESULT_CONVERTER, et - st))
                    output = p.stdout.decode().split('\n')
                    if len(output) > 1:
                        log.trace("execute", output[-2])
                except subprocess.TimeoutExpired as e:
                    msg = 'execute %s timeout' % SCAN_RESULT_CONVERTER
                    log.trace("execute", msg)
                    raise XcalException('ScanReporterService', 'execute', msg, TaskErrorNo.E_SRV_V2CSF_EXEC_TIMEOUT)

                if p.returncode != 0:
                    msg = 'execute %s failed, exit(%d)' % (SCAN_RESULT_CONVERTER, p.returncode)
                    log.trace("execute", msg)
                    raise XcalException('ScanReporterService', 'execute', msg, TaskErrorNo.E_SRV_V2CSF_EXEC_FAILED)

                csf_file_path = os.path.join(self.scan_work_dir, 'xvsa-xfa-dummy.csf')
                if not os.path.exists(csf_file_path):
                    msg = 'execute %s failed, cannot generate output file: %s' % (SCAN_RESULT_CONVERTER, csf_file_path)
                    log.trace("execute", msg)
                    raise XcalException('ScanReporterService', 'execute', msg, TaskErrorNo.E_SRV_CSF_NOT_EXISTS)

                log.trace("execute", 'complete convert scan result')

                log.trace("execute", 'starting import scan result')
                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT, Status.PROCESSING, Percentage.START, 'import scan result')
                file_info_file_id = AgentInvoker.extract_remote_file_id(self.task_config, FILE_INFO_FILE_NAME)
                upload_result = self.comms.upload_scan_result(self.scan_id, self.scan_work_dir, file_info_id=file_info_file_id)

                if upload_result > 0:
                    upload_result_success_number = int(self.task_config.get('uploadResultSuccessNumber')) + upload_result
                    self.task_config.set('uploadResultSuccessNumber', str(upload_result_success_number))

                ScanMetrics.push_to_gateway(push_gateway_url, job='scanTaskService', reg=registry)
            except XcalException as e:
                log.error(e.service, e.operation, e.message)
                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT, Status.FAILED, Percentage.END, e.message, e.err_code)
            except Exception as e:
                logging.exception(e)
                log.error("ScanReporterService", "execute", "unexpected exception: %s" % str(e))
                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT, Status.FAILED, Percentage.END, "import scan result failed, unexpected exception occurs", -1)


class PackageScanResultService(object):
    def __init__(self, logger:XcalLogger, task_config:ConfigObject):
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def execute(self):
        with XcalLogger(str(PackageScanResultService.__name__), str(PackageScanResultService.execute.__name__),
                        parent = self.logger) as log:

            self.comms.upload_progress(self.scan_id, Stage.SCANNING, Status.PROCESSING, Percentage.MIDDLE,
                                       "begin to package scan result")

            scan_work_dir = os.path.join(BASE_SCAN_PATH, self.scan_id)
            scan_result_file = os.path.join(scan_work_dir, "%s.v" % self.scan_id)
            scan_result_archive = os.path.join(scan_work_dir, "%s.tar.gz" % self.scan_id)

            if not os.path.exists(scan_result_file):
                log.error("PackageScanResultService", "execute", "scan result does not exist, scan result: %" % scan_result_file)
                raise XcalException("PackageScanResultService", "execute",
                                    "scan result file does not exist", TaskErrorNo.E_NO_SCAN_RESULT)

            CompressionUtility.compress_tar_package(log, scan_result_file, scan_result_archive)

            if not os.path.exists(scan_result_archive):
                log.error("PackageScanResultService", "execute", "scan result archive does not exist, scan result: %" % scan_result_archive)
                raise XcalException("PackageScanResultService", "execute",
                                    "scan result archive does not exist", TaskErrorNo.E_NO_SCAN_RESULT)

            self.comms.upload_progress(self.scan_id, Stage.SCANNING, Status.PROCESSING, Percentage.END,
                                       "end to package scan result")


class UploadDiagnosticInfoService(object):
    def __init__(self, logger:XcalLogger, task_config):
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.task_config = task_config
        self.scan_work_dir = os.path.join(BASE_SCAN_PATH, self.scan_id)

    def execute(self):
        """
        Upload the diagnostic info to Java Web Api
        """
        with XcalLogger(str(UploadDiagnosticInfoService.__name__), str(UploadDiagnosticInfoService.execute.__name__), parent=self.logger) as log:
            XcalInternalCommunicator(log, self.task_config).upload_diagnostic_info_to_webapi(self.scan_id, self.scan_work_dir)


class RemoteResultUploader(object):
    def __init__(self, logger: XcalLogger, task_config, stage: dict):
        self.logger = logger
        self.scan_id = task_config.get("scanTaskId")
        self.task_config = task_config
        self.scan_work_dir = os.path.join(BASE_SCAN_PATH, self.scan_id)
        self.stage = stage
        self.comms = XcalInternalCommunicator(self.logger, task_config)

    def execute(self):
        """
        Upload the defects to Java Web Api
        :return: the number of upload scan results successful
        """
        with XcalLogger(str(RemoteResultUploader.__name__), str(RemoteResultUploader.execute.__name__),
                        parent=self.logger) as log:

            self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT, Status.PROCESSING,
                                       Percentage.MIDDLE, "starting upload remote scan result")
            # Extract Info
            remote_result_file_id = AgentInvoker.extract_remote_file_id(self.task_config, SPOTBUGS_RESULT_V_FILE_TEMP_NAME)
            if remote_result_file_id is None:
                self.logger.trace("No remotely generated result was found, skipping upload", "")
                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT, Status.PROCESSING, Percentage.END,
                                           "no remote scan result was found, skipping upload")
            else:
                download_res_temp_filename = os.path.join(self.scan_work_dir, REMOTE_RESULT_V_FILE_TEMP_NAME)
                self.logger.trace("Found valid remotely generated scan result fileId = %s. Downloading it to %s" %
                                       (remote_result_file_id, download_res_temp_filename), "")

                # Download from FileService
                RemoteFileService(self.task_config, self.logger).fetch_file_with_token(remote_result_file_id,
                                                                             download_res_temp_filename,
                                                                             self.task_config)

                self.logger.trace("Download completed %s, start uploading to web-api" % (download_res_temp_filename), "")

                # Upload to Java API
                upload_result = XcalInternalCommunicator(log, self.task_config).upload_scan_result(self.scan_id, self.scan_work_dir, scan_result=download_res_temp_filename)
                if upload_result != 0:
                    upload_result_success_number = int(
                        self.task_config.get("uploadResultSuccessNumber")) + upload_result
                    self.task_config.set("uploadResultSuccessNumber", str(upload_result_success_number))

                self.comms.upload_progress(self.scan_id, Stage.IMPORT_RESULT, Status.PROCESSING, Percentage.END,
                                           "upload remote scan result done")
