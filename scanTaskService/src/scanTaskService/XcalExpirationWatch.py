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

import threading
from enum import Enum

from common.XcalLogger import XcalLogger
from scanTaskService.Config import AGENT_CONNECT_EXPIRE_DURATION, \
    SCAN_CONTROLLER_STAGE_INTERVAL, TaskErrorNo
from scanTaskService.util.TimeUtility import TimeUtility
from common.XcalException import XcalException


class ExpireHookType(Enum):
    EXPIRE_CONNECT_AGENT = 1
    EXPIRE_NOW = 5
    EXPIRE_IGNORE = 6  # only used inside expire related procedures to avoid recursive expiration
    EXPIRE_NEXT_STAGE = 7


class ExpirationWatcher(object):
    expire_list = []
    lock = threading.RLock()

    def __init__(self, logger: XcalLogger):
        self.logger = XcalLogger("ExpirationWatcher", "__init__", parent=logger)

    def add_expiration_hook(self, job_id:str, job_name:str, job_detail_config:dict, expire:int = 0, hook_type:ExpireHookType = None):
        """
        Add a expiration hook to the timer system, which would be
         spotted by the ExpiredTaskRemover, and triggered a response there.
        :param job_id: JOB_ID, usually UUID
        :param job_name:
        :param job_detail_config:
        :param expire: integer, absolute expiration timestamp, in UTC seconds,
                        i.e. use delta + TimeUtilities.get_utc_timestamp()
        :param hook_type: replacement for expire, which
        :return:
        """
        ExpirationWatcher.lock.acquire()
        if expire == 0 and hook_type is None:
            raise XcalException("ExpirationWatcher", "add_expiration_hook", "Invalid parameters in add_expiration_hook",
                                TaskErrorNo.E_UTIL_EXPIRE_NONE_HOOKTYPE)
        elif expire == 0 and hook_type is not None:
            expire = self.get_timeout_interval(job_detail_config, hook_type) + TimeUtility().get_utc_timestamp()

        # Used inside expiration related processes
        if hook_type is not None and hook_type == ExpireHookType.EXPIRE_IGNORE:
            return

        self.logger.trace("ExpirationWatcher, add job = %s, jobId = %s, expiring at %d" % (job_name, job_id, int(expire)), "")
        ExpirationWatcher.expire_list.append({"jobId": job_id, "job": job_name,"expire": expire, "config": job_detail_config})
        self.logger.debug("appended expire_list = ", ExpirationWatcher.expire_list.copy())
        self.logger.debug("Exiting add_expiration_hook, expire_list = %d" % id(ExpirationWatcher.expire_list), "")
        ExpirationWatcher.lock.release()
        pass

    def remove_by_id(self, job_id:str):
        """
        Remove a job with its according job_id
        :param job_id:
        :return:
        """
        ExpirationWatcher.lock.acquire()
        work_list = ExpirationWatcher.expire_list.copy()
        origin_list = work_list.copy()
        self.logger.trace("trying to remove jobId = %s inside expire list" % job_id, "")
        self.logger.debug("trying to filter through expire list =", origin_list)
        for item in work_list:
            if item.get('jobId') == job_id:
                work_list.remove(item)

        # expire_new_list = [x for x in work_list if (x.get('jobId') != job_id)]
        self.logger.debug("filtered expire list = ", work_list)

        if len(origin_list) > len(work_list):
            self.logger.debug("remove a hook due to message arrival jobId = %s, old = %d, new = %d"
                                    % (job_id, len(origin_list), len(work_list)), "")
        else:
            self.logger.error("ExpirationWatcher", "remove_by_id",
                              "remove jobId = %s inside expire list failed, still got list old = %d(%s), now = %d(%s)" %
                              (job_id, len(origin_list), str(id(origin_list)), len(work_list), id(work_list)))
        ExpirationWatcher.expire_list = work_list
        self.logger.debug("Exiting remove_by_id, expire_list = %d" % id(ExpirationWatcher.expire_list), "")
        ExpirationWatcher.lock.release()
        pass

    def pop_expired_list(self):
        """
        Pop an expired list with expired jobs in the returned list
        :return: a list containing expired entries:
                 i.e.   {"job":"JOB_LIST_NAME", "jobId":"uuid", "config", "DETAIL_CONFIG"}
        """
        ExpirationWatcher.lock.acquire()
        utc_timestamp = TimeUtility().get_utc_timestamp()
        old_list_len = len(ExpirationWatcher.expire_list)

        changed = False
        expired = []

        for one_item in ExpirationWatcher.expire_list:
            if utc_timestamp > int(one_item.get("expire")):
                self.logger.trace("ExpirationWatcher, expiring one item "
                                  " (expire = %d, now = %d), jobId = %s... " %
                                  (int(one_item.get("expire")), utc_timestamp, one_item.get("jobId")), "")
                expired.append(one_item)
                ExpirationWatcher.expire_list.remove(one_item)
                changed = True
        if changed:
            self.logger.debug("ExpirationWatcher, change detected... origin list = %d new list len = %d " % (
                old_list_len, len(ExpirationWatcher.expire_list)), "")
        self.logger.debug("Exiting pop_expired_list, expire_list = %d, thread = %s" % (id(ExpirationWatcher.expire_list), threading.current_thread().ident),"")
        ExpirationWatcher.lock.release()
        return expired

    def get_timeout_interval(self, task_info, exp_type:ExpireHookType):
        """
        Get the timeout interval set for each type of expire watcher
        :param task_info:
        :param exp_type:
        :return:
        """
        if exp_type == ExpireHookType.EXPIRE_IGNORE:
            raise XcalException("ExpirationWatcher", "get_timeout_interval", "ExpireType = IGNORE was given to get a duration",
                                TaskErrorNo.E_UTIL_EXPIRE_IGNORE_DURATION)
        # This is used for agent connection
        elif exp_type == ExpireHookType.EXPIRE_CONNECT_AGENT:
            return AGENT_CONNECT_EXPIRE_DURATION
        # This was used for expiration between task stages inside a pipeline
        elif exp_type == ExpireHookType.EXPIRE_NEXT_STAGE:
            return SCAN_CONTROLLER_STAGE_INTERVAL
        elif exp_type == ExpireHookType.EXPIRE_NOW:
            return 0
        else:
            return 1
