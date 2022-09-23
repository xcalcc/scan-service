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


import json
import logging
import uuid

from common.XcalLogger import XcalLogger
from scanTaskService.Config import TOPIC_PREFIX, TaskErrorNo
from scanTaskService.XcalExpirationWatch import ExpirationWatcher, ExpireHookType
from scanTaskService.util.KafkaUtility import KafkaUtility
from scanTaskService.util.TimeUtility import TimeUtility
from common.XcalException import XcalException


class JobInitiator(object):
    def __init__(self, logger: XcalLogger):
        self.parent_logger = logger
        pass

    def initiate_job_flow(self, job_name, job_detail_config: dict, expire_type: ExpireHookType):
        """
        Send the job to Kafka, and add to expiration watcher
        :param expire_type:
        :param job_name:
        :param job_detail_config:
        :return:
        """
        with XcalLogger("JobInitiator", "initiate_job_flow", parent=self.parent_logger) as log:
            current_time = TimeUtility().get_utc_timestamp()
            if expire_type != ExpireHookType.EXPIRE_IGNORE:
                expiration = ExpirationWatcher(log).get_timeout_interval(job_detail_config, expire_type) + current_time
            else:
                # Ignore the timeout situation, do not add to expire list.
                expiration = -1

            job_id = str(uuid.uuid1())
            job_item = {"expire": expiration, "config": job_detail_config, "job": job_name, "jobId": job_id}

            log.trace("JobInitiator.initiating flow on %d, ==> JOB_ID = %s, JOB_NAME = %s " % (
                current_time, job_id, job_name), str(json.dumps(job_detail_config)))

            # Adding Expiration Watch
            if expire_type != ExpireHookType.EXPIRE_IGNORE:
                log.trace("Initiating a flow which add an expiration = %d" % expiration, "")
                ExpirationWatcher(log).add_expiration_hook(job_id, job_name, job_detail_config, expiration)
            KafkaUtility.kafka_publish(TOPIC_PREFIX + job_name, json.dumps(job_item))
        pass


class JobListener(object):
    def __init__(self, logger: XcalLogger):
        # self.logger = logger
        self.consumer = None
        pass

    def poll_job_task(self, job_list_name: str, max_entries: int = 1):
        received_list = []
        try:
            topic = TOPIC_PREFIX + job_list_name
            if self.consumer is None:
                self.consumer = KafkaUtility.get_kafka_consumer(topic)
            received_list = KafkaUtility.kafka_receive(topic, max_entries=max_entries, consumer=self.consumer)
        except Exception as e:
            logging.exception(
                XcalException("JobListener", "poll_job_task", ("Error arisen in communicating with Kafka", e),
                              TaskErrorNo.E_SRV_JOBLISTEN_KAFKA_RECEIVE))
            # self.logger.warn("Error arisen in communicating with Kafka", "")

        jobs = []
        current_time = TimeUtility().get_utc_timestamp()
        for one_msg in received_list:
            # self.logger.trace("poll_job_task", "found one message: offset = %d" % one_msg.offset)
            data_obj = json.loads(one_msg.value.decode("UTF-8"))
            config = data_obj.get("config")
            # Removing Expiration Watch
            with XcalLogger("JobListener", "poll_job_task") as log:
                ExpirationWatcher(log).remove_by_id(data_obj.get("jobId"))
                if int(data_obj.get("expire")) != -1 and current_time > int(data_obj.get("expire")):
                    # self.logger.warn("skipped a timeout (expire = %d , now = %d) job within list(%s) id = %s" %
                                    #(int(data_obj.get("expire")), current_time, job_list_name, data_obj.get("jobId")), "")
                    # Jobs would be empty in this case, from beginning of loop entry
                    pass
                else:
                    # self.logger.trace("poll_job_task", "adding one job to do: id = %s" % data_obj.get("jobId"))
                    jobs.append(config)
        return jobs
    
    def commit_job_task(self):
        KafkaUtility.commit(consumer=self.consumer)


class JobTimeoutManager(object):
    def __init__(self, logger):
        self.logger = logger
        pass

    def start_timeout(self, job_list_name:str, config_dict:dict, expire_type:ExpireHookType = None, timeout_seconds:int=0):
        """
        Starting the timer and set the timeout control of the config.
        :param job_list_name:
        :param config_dict:
        :param expire_type:
        :param timeout_seconds:
        :return:
        """
        curtime = TimeUtility().get_utc_timestamp()
        if expire_type is not None:
            expiration = ExpirationWatcher(self.logger).get_timeout_interval(config_dict, expire_type) + curtime
        else:
            expiration = timeout_seconds + curtime

        job_id = str(uuid.uuid1())

        self.logger.trace(
            "JobTimeoutManager.starting timeout %d, which expire at %d ==> JOB_ID = %s, JOB_LIST = %s" % (curtime, expiration, job_id, job_list_name), str(json.dumps(config_dict)))

        original_man = list()
        original_man.append({"jobId":job_id, "jobListName": job_list_name, "expire":expiration})
        config_dict["timeoutMan"] = original_man
        ExpirationWatcher(self.logger).add_expiration_hook(job_id, job_list_name, config_dict, expiration)
        return job_id

    def complete_task(self, config_dict: dict):
        """
        Complete the task and remove the task from Timer list
        :param config_dict:
        :return:
        """
        removed_count = 0
        original_man = config_dict.get("timeoutMan", [])
        for timeout_item in original_man:
            if timeout_item.get("jobId") is not None:
                self.logger.trace(
                    "JobTimeoutManager.complete JOB_ID = %s" % (timeout_item.get("jobId")), "")
                ExpirationWatcher(self.logger).remove_by_id(timeout_item.get("jobId"))
                removed_count += 1
        config_dict["timeoutMan"] = []
        return removed_count

    def complete_task_with_id(self, job_id:str):
        """
        Complete the task and remove timer from list
        :param job_id: The job to be cancelled.
        :return:
        """
        ExpirationWatcher(self.logger).remove_by_id(job_id)
        pass

    def is_expired(self, config_dict):
        """
        Is the task has expired?
        :param config_dict:
        :return:
        """
        original_man = config_dict.get("timeoutMan", [])
        for timeout_item in original_man:
            current_time = TimeUtility().get_utc_timestamp()
            if (timeout_item.get("expire") is not None) and current_time > int(timeout_item.get("expire")):
                return True
        return False

    def override_timeout_from_user_config(self, config_dict:dict, default_timeout:int, stage_type:str):
        if config_dict.get("stageTimeout") is not None:
            timeout_config = json.loads(config_dict.get("stageTimeout"))
            for k, v in timeout_config.items():
                if k == stage_type:
                    return float(v)
        return default_timeout