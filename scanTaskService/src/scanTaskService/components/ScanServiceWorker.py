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


import logging
import threading
import time
import uuid

from common.CommonGlobals import Stage, Status, Percentage

from common.ConfigObject import ConfigObject
from common.XcalLogger import XcalLogger
from scanTaskService.Config import SCAN_RUNNER_JOB_TOPIC, TaskErrorNo, SCANNER_WORKER_TIMEOUT_LIST, AGENT_TOPIC_PREFIX, \
    SCAN_ENGINE_TOPIC, SCANNER_WORKER_COUNT, TOPIC_PREFIX
from scanTaskService.XcalExpirationWatch import ExpirationWatcher
from scanTaskService.components import LoggingHandler
from scanTaskService.components.AgentInfo import AgentInfoManagement, AgentInfoStatus
from scanTaskService.components.JobInitiator import JobListener
from scanTaskService.components.ScanController import ScanController
from scanTaskService.components.XcalServices import ScanStageObject


class ExpiredTaskRemover(object):
    def __init__(self):
        pass

    def loop(self):
        LoggingHandler.ban_kafka_loggings()
        # Looping to receive data -----------------------
        while True:
            try:
                self.process()
            except KeyboardInterrupt:
                logging.warning("Exiting, Bye!")
                return
            except Exception as err:
                logging.exception(err)
                one_logger = XcalLogger("ExpiredTaskRemover", "loop")
                one_logger.error("ExpiredTaskRemover", "loop", ("Process failed...", str(err)))
            time.sleep(1)

    def process(self):
        with XcalLogger("ExpiredTaskRemover", "process") as remove_log:
            expired = ExpirationWatcher(remove_log).pop_expired_list()
            for one_expire_item in expired:
                # If this is a pipeline object, execute this accordingly
                remove_log.trace("Found a job that was timeout",
                                 ("item = ", str(one_expire_item)))
                if one_expire_item.get("job") == SCAN_RUNNER_JOB_TOPIC:
                    # Scanner Worker Job
                    copied_item = self.get_scanner_worker_expire_task(one_expire_item, TaskErrorNo.E_QUEUEING_EXPIRED)
                elif one_expire_item.get("job") == SCANNER_WORKER_TIMEOUT_LIST:
                    copied_item = self.get_scanner_worker_expire_task(one_expire_item, TaskErrorNo.E_SCAN_SERVICE_STAGE_TIMEOUT)
                elif str(one_expire_item.get("job")).startswith(AGENT_TOPIC_PREFIX):
                    copied_item = self.get_expire_task_due_to_no_agent_do(one_expire_item)
                else:
                    remove_log.error("ExpiredTaskRemover", "process", "Cannot report expiration, due to unknown kind of job_list is present")
                    copied_item = self.get_scanner_worker_expire_task(one_expire_item, TaskErrorNo.E_UTIL_EXPIRE_UNKNOWN_LIST_NAME)

                # Immediate invoke the processing ScanController, fix bug #781 #941
                remove_log.trace(
                    "Adding a pipeline for reporting the timeout", "scanTaskId = %s" % copied_item.get("scanTaskId"))
                # ScanController(remove_log).process_internal_job(copied_item, no_timeout=True)
                ScanController(remove_log, ConfigObject(copied_item)).sp_start()
            pass

    def start(self):
        with XcalLogger("ExpiredTaskRemover", "start") as one_logger:
            one_logger.trace("ExpireTaskRemover.start", "Starting an ExpiredTaskRemover on object.id=(%d)" % id(self))
        th = threading.Thread(target=ExpiredTaskRemover.loop, args=(self, ))
        th.setDaemon(True)
        th.setName("ExpiredTaskRemover-1-" + str(uuid.uuid1()))
        th.start()

    def get_scanner_worker_expire_task(self, one_expire_item:dict, err:TaskErrorNo):
        copied_item = one_expire_item.get("config").copy()
        common_suffix = " scanServiceJobId = %s, timeout = %s" % (str(one_expire_item.get("jobId")),
                                    str(one_expire_item.get("expire")))
        if copied_item.get("pipeline") is None or copied_item.get("pipelineOffset") is None:
            extra_info = "No pipeline or ofst %s" % common_suffix
        elif len(copied_item.get("pipeline")) <= int(copied_item.get("pipelineOffset")):
            extra_info = "Unacceptable pipelineOffset %s" % common_suffix
        else:
            extra_info = "In stage %s, %s" % \
                             (copied_item.get("pipeline")[int(copied_item.get("pipelineOffset"))].get("type"),
                              common_suffix)

        copied_item["pipeline"] = [
            ScanStageObject(stage_type="uploadProgress", info={}, start=5, complete=100, sync=0, timeout=10).as_dict()]
        copied_item["pipelineOffset"] = 0
        copied_item["agentName"] = "timeout-checker"
        copied_item["target"] = "progress"
        copied_item["errorInfo"] = err
        copied_item["extraInfo"] = extra_info
        copied_item["timeoutMan"] = []
        copied_item["origin"] = "scanService"
        copied_item["stage"] = Stage.SCANNING
        copied_item["status"] = Status.FAILED
        copied_item["progress"] = Percentage.END
        return copied_item

    def get_expire_reason(self, job_name):
        return AgentInfoManagement.get_agent_info_status(job_name)

    def get_error_info(self, job_name):
        expire_reason = self.get_expire_reason(job_name)
        if expire_reason == AgentInfoStatus.NO_AGENT:
            logging.warning("no active agent")
            err = TaskErrorNo.E_NO_ACTIVE_AGENT_FOR_THIS_JOB
        elif expire_reason == AgentInfoStatus.AGENT_IS_BUSY:
            logging.warning("agent is busy")
            err = TaskErrorNo.E_AGENT_IS_BUSY
        elif expire_reason == AgentInfoStatus.JOB_QUEUE_NAME_NOT_SUPPORT:
            logging.warning("no active agent for this job")
            err = TaskErrorNo.E_NO_ACTIVE_AGENT_FOR_THIS_JOB
        else:
            logging.error("unknown, need to check the scan service logs")
            err = TaskErrorNo.E_COMMON_UNKNOWN_ERROR

        return err

    def get_expire_task_due_to_no_agent_do(self, expire_item: dict):
        job_config = expire_item.get("config").copy()
        common_suffix = " scanServiceJobId = %s, timeout = %s" % (str(expire_item.get("jobId")),
                                                                  str(expire_item.get("expire")))
        job_name = str(expire_item.get("job"))
        if job_name.startswith(AGENT_TOPIC_PREFIX):
            job_name = job_name[len(AGENT_TOPIC_PREFIX):]
            if job_name.startswith(TOPIC_PREFIX):
                job_name = job_name[len(TOPIC_PREFIX):]

        err = self.get_error_info(job_name)

        # Merging TaskConfig with JobConfig
        task_config = job_config.get("taskConfig", {})
        job_config = ConfigObject.merge_two_dicts(job_config, task_config)

        job_config["pipeline"] = [
            ScanStageObject(stage_type = "uploadProgress", info = {}, start = 5, complete = 100, sync = 0,
                            timeout = 10).as_dict()]
        job_config["pipelineOffset"] = 0
        job_config["target"] = "progress"
        job_config["errorInfo"] = err
        job_config["extraInfo"] = common_suffix
        job_config["timeoutMan"] = []
        job_config["stage"] = Stage.AGENT_START
        job_config["status"] = Status.FAILED
        job_config["progress"] = Percentage.END
        return job_config


class TimerProcessAgentInfo(object):
    @staticmethod
    def loop():
        while True:
            try:
                AgentInfoManagement.clean_timeout_agent()
            except KeyboardInterrupt:
                logging.warning("Exiting, Bye!")
                return
            except Exception as err:
                logging.exception(err)
                one_logger = XcalLogger("TimerProcessAgentInfo", "loop")
                one_logger.error("TimerProcessAgentInfo", "loop",
                                 ("Process failed...", str(err)))
            time.sleep(5)

    @staticmethod
    def start():
        with XcalLogger("TimerProcessAgentInfo", "start") as one_logger:
            one_logger.trace("TimerProcessAgentInfo.start", "Starting an TimerProcessAgentInfo")
        th = threading.Thread(target = TimerProcessAgentInfo.loop)
        th.setDaemon(True)
        th.setName("Thread-TimerProcessAgentInfo")
        th.start()


# This class was used only for debugging & memory dumps, see git log to find histories
class HealthCheck(object):
    def __init__(self):
        pass

    def start(self):
        pass


class ScanServiceJobListener(object):
    workers = []

    def __init__(self):
        pass

    def process_job(self):
        # Looping to poll info from message queue
        LoggingHandler.ban_kafka_loggings()
        log = XcalLogger("ScanServiceJobListener", "process_job")
        listener = JobListener(log)
        # controller = ScanController(XcalLogger("ScanServiceJobListener", "process_job"),
        #                                         type=ControllerType.DEFAULT_ASYNC)
        while True:
            try:
                lst = listener.poll_job_task(SCAN_RUNNER_JOB_TOPIC, 1)
                for message in lst:
                    # controller.process_internal_job(message)
                    ScanController(XcalLogger('ScanServiceJobListener', 'process_job'), ConfigObject(message)).sp_start()
            except KeyboardInterrupt:
                logging.warning("Exiting, Bye!")
                return
            except Exception as err:
                logging.exception(err)
                log.error("ScanServiceJobListener", "process_job",
                              ("kafka receive / process job failed...", str(err)))
                # Fix zentao bug #928, avoid CPU usage being too high when above mechanism falls through.
                time.sleep(3)
            finally:
                listener.commit_job_task()
            time.sleep(0.5)

    # Single worker by default
    def start_workers(self, count: int = SCANNER_WORKER_COUNT):
        for one in range(count):
            th = threading.Thread(target=ScanServiceJobListener.process_job, args=(self,))
            th.setDaemon(True)
            th.setName("ScannerWorker-" + str(one) + "-" + str(uuid.uuid1()))
            th.start()
            ScanServiceJobListener.workers.append(th)


class ScanEngineServiceJobListener(object):
    workers = []

    def __init__(self):
        pass

    def process_job(self):
        # Looping to receive data -----------------------
        LoggingHandler.ban_kafka_loggings()
        log = XcalLogger("ScanEngineServiceJobListener", "process_job")
        listener = JobListener(log)
        # controller = ScanController(XcalLogger("ScanEngineServiceJobListener", "process_job"),
        #                                         type=ControllerType.SCAN_ENGINE)
        while True:
            try:
                lst = listener.poll_job_task(SCAN_ENGINE_TOPIC, 1)
                for message in lst:
                    # controller.process_internal_job(message)
                    ScanController(XcalLogger('ScanEngineServiceJobListener', 'process_job'), ConfigObject(message)).sp_start()
            except KeyboardInterrupt:
                logging.warning("Exiting, Bye!")
                return
            except Exception as err:
                logging.exception(err)
                log.error("ScanEngineServiceJobListener", "process_job",
                          "BaseException in resolving previous exception")
                time.sleep(3)
            finally:
                listener.commit_job_task()
            time.sleep(0.5)

    # Single worker by default
    def start_workers(self, count: int = SCANNER_WORKER_COUNT):
        for one in range(count):
            th = threading.Thread(target=ScanEngineServiceJobListener.process_job, args=(self,))
            th.setDaemon(True)
            th.setName("ScanEngineWorker-" + str(one) + "-" + str(uuid.uuid1()))
            th.start()
            ScanEngineServiceJobListener.workers.append(th)