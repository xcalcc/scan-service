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


import datetime
import logging
import threading
from enum import Enum

from common.CommonGlobals import TaskErrorNo
from common.XcalException import XcalException
from scanTaskService.Config import AGENT_TIMEOUT


class AgentWorkerStatus(Enum):
    IDLE = 0
    BUSY = 1


class AgentStatus(Enum):
    IDLE = 0
    BUSY = 1


class AgentInfoStatus(Enum):
    NO_AGENT = 0
    AGENT_IS_BUSY = 1
    JOB_QUEUE_NAME_NOT_SUPPORT = 2
    UNKNOWN = 3


class AgentWorkerInfo(object):
    def __init__(self, worker_id: str, worker_name: str, status: AgentWorkerStatus, pid: int, scan_task_id: str = None):
        self.worker_id = worker_id
        self.worker_name = worker_name
        self.status = status
        self.pid = pid
        self.scan_task_id = scan_task_id

        now = datetime.datetime.now()

        self.created_on = now
        self.modified_on = now

    def __str__(self):
        return "worker_id: %s, worker_name: %s, status: %s, scan_task_id: %s, pid: %s" % (
            self.worker_id, self.worker_name, self.status, self.scan_task_id, self.pid)


class AgentInfo(object):
    def __init__(self, agent_id: str, agent_name: str, username: str, supported_job_queue_name: list,
                 total_worker_num: int, worker_info_dict: dict, created_on: datetime.datetime,
                 modified_on: datetime.datetime, status: AgentStatus = AgentStatus.IDLE, worker_num: int = 0):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.username = username
        self.status = status
        self.supported_job_queue_name = supported_job_queue_name
        self.total_worker_num = total_worker_num
        self.worker_num = worker_num    # current worker number
        self.worker_info_dict = worker_info_dict
        self.created_on = created_on
        self.modified_on = modified_on

    def __str__(self):
        return "agent_id: %s, agent_name: %s, supported_job_queue_name: %s, total_worker_num: %s, status: %s" % (
            self.agent_id, self.agent_name, self.supported_job_queue_name, self.total_worker_num, self.status)


class AgentInfoManagement(object):
    """
    manage the agent info
    """
    agent_info_dict = dict()    # k:v is agent_id: gentInfo object
    lock = threading.RLock()

    @staticmethod
    def update_agent_info(agent_id: str, agent_name: str, username: str, supported_job_queue_name: list,
                          total_worker_num: int, worker_info: AgentWorkerInfo):
        AgentInfoManagement.lock.acquire()

        agent_info = AgentInfoManagement.agent_info_dict.get(agent_id)
        now = datetime.datetime.now()

        if agent_info:  # not new agent info
            if agent_info.worker_info_dict.get(worker_info.worker_id):
                # not new agent worker info, update its corresponding worker info
                agent_info.worker_info_dict.get(worker_info.worker_id).status = worker_info.status
                agent_info.worker_info_dict.get(worker_info.worker_id).scan_task_id = worker_info.scan_task_id
                agent_info.worker_info_dict.get(worker_info.worker_id).modified_on = now

                # agent status is busy only when all worker is busy
                if agent_info.total_worker_num == agent_info.worker_num:
                    busy_worker_num = 0
                    for key in agent_info.worker_info_dict:
                        if agent_info.worker_info_dict[key].status == AgentWorkerStatus.BUSY:
                            busy_worker_num += 1

                    if busy_worker_num == agent_info.total_worker_num:
                        agent_info.status = AgentStatus.BUSY

            else:   # new agent worker info
                agent_info.worker_info_dict[worker_info.worker_id] = worker_info
                agent_info.worker_num += 1
                agent_info.status = AgentStatus.IDLE
                agent_info.modified_on = now

            agent_info.total_worker_num = total_worker_num
            if agent_info.total_worker_num < agent_info.worker_num:
                logging.error("agent_info.total_worker_num should >= agent_info.worker_num,"
                              " please check the scan service log")

        else:   # new agent info
            worker_info_dict = dict()
            worker_info_dict[worker_info.worker_id] = worker_info
            agent_info = AgentInfo(agent_id, agent_name, username, supported_job_queue_name, total_worker_num,
                                   worker_info_dict, created_on = now, modified_on = now, status = AgentStatus.IDLE)
            agent_info.worker_num += 1

        AgentInfoManagement.agent_info_dict[agent_id] = agent_info

        AgentInfoManagement.lock.release()

    @staticmethod
    def remove_terminate_agent_info(agent_id: str, status: str):
        AgentInfoManagement.lock.acquire()

        agent_info = AgentInfoManagement.agent_info_dict.get(agent_id)
        if agent_info and status == "terminate":
            del AgentInfoManagement.agent_info_dict[agent_id]

        AgentInfoManagement.lock.release()

    @staticmethod
    def get_agent_info_status(job_queue_name: str = None):
        """

        :param job_queue_name:
        :return: agent info status
        """
        AgentInfoManagement.lock.acquire()

        if job_queue_name is None:
            logging.error("job_queue_name: %s" % job_queue_name)
            raise XcalException("AgentInfo", "get_agent_info_status", "job_queue_name must be provided",
                                TaskErrorNo.E_COMMON_INVALID_VALUE)

        logging.info("job_queue_name: %s" % job_queue_name)
        logging.info("agent_info_dict: %s" % AgentInfoManagement.agent_info_dict)

        # agent support current job queue name is busy doing other jobs
        # no agent support current job queue name
        # no agent connect to the server currently
        reason = AgentInfoStatus.UNKNOWN
        if not AgentInfoManagement.agent_info_dict:
            logging.warning("no active agent")
            reason = AgentInfoStatus.NO_AGENT
        else:
            job_queue_name_is_supported = False
            support_job_queue_name_agent_number = 0
            support_job_queue_name_busy_agent_number = 0
            for key in AgentInfoManagement.agent_info_dict:
                if job_queue_name in AgentInfoManagement.agent_info_dict[key].supported_job_queue_name:
                    job_queue_name_is_supported = True
                    support_job_queue_name_agent_number += 1
                    logging.info("%s status: %s" %
                                 (AgentInfoManagement.agent_info_dict[key].agent_name,
                                  AgentInfoManagement.agent_info_dict[key].status))
                    if AgentInfoManagement.agent_info_dict[key].status == AgentStatus.BUSY:
                        support_job_queue_name_busy_agent_number += 1
                        logging.info("%s is busy" %
                                     AgentInfoManagement.agent_info_dict[key].agent_name)

            logging.debug("support_job_queue_name_agent_number: %s, support_job_queue_name_busy_agent_number: %s" %
                            (support_job_queue_name_agent_number, support_job_queue_name_busy_agent_number))
            if not job_queue_name_is_supported:
                reason = AgentInfoStatus.JOB_QUEUE_NAME_NOT_SUPPORT
            elif support_job_queue_name_agent_number == support_job_queue_name_busy_agent_number:
                reason = AgentInfoStatus.AGENT_IS_BUSY

        AgentInfoManagement.lock.release()

        return reason

    @staticmethod
    def clean_timeout_agent():
        """
        remove the agent info when the agent info is not modified than AGENT_TIMEOUT seconds
        :return:
        """
        now = datetime.datetime.now().timestamp()
        logging.debug("clean_timeout_agent")

        AgentInfoManagement.lock.acquire()
        for agent_id in list(AgentInfoManagement.agent_info_dict.keys()):
            if AgentInfoManagement.agent_info_dict[agent_id].modified_on.timestamp() + AGENT_TIMEOUT < now:
                del AgentInfoManagement.agent_info_dict[agent_id]

        logging.debug("agent info dict len: %s" % len(AgentInfoManagement.agent_info_dict))
        AgentInfoManagement.lock.release()