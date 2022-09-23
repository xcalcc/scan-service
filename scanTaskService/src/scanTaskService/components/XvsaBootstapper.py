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
import os

from common.CommonGlobals import FILE_INFO_FILE_NAME, BASE_SCAN_PATH
from common.XcalLogger import XcalLogger
from common.ConfigObject import ConfigObject
from scanTaskService.util.DockerUtility import DockerUtility
from scanTaskService.util.GuidUtility import guid
from common.TokenExtractor import TokenExtractor
from scanTaskService.Config import ScanTaskServiceAPIData, TaskErrorNo, SCAN_ENGINE_TOPIC, \
    SCAN_DOCKER_MEM_LIMIT, scanSourceFileSize, scanSourceFileLines, \
    scanSourceFileCount
from common.XcalException import XcalException
from scanTaskService.XcalExpirationWatch import ExpireHookType
from scanTaskService.components.JobInitiator import JobInitiator


class XvsaDockerExecutor(object):
    def __init__(self, logger: XcalLogger):
        self.logger = logger

    @staticmethod
    def construct_scan_container_name(task_config: ConfigObject):
        """
        container name: scan_{projectId}_{scan_task_id: 8 chars}_{time}
        :param task_config:
        :return:
        """
        with XcalLogger("XvsaEngineBootstrapper", "construct_scan_container_name") as log:
            log.trace("construct_scan_container_name", "project_id: %s, scan_task_id: %s" % (task_config.get('projectId'), task_config.get('scanTaskId')))
            project_id = task_config.get('projectId')
            scan_task_id = task_config.get('scanTaskId')

            if project_id is None:
                log.logger.error("XvsaDockerExecutor", "construct_scan_container_name",
                                "invalid project_id, project_id: %s" % project_id)
                raise XcalException("XvsaDockerExecutor", "construct_scan_container_name", "invalid project_id, project_id: %s" % project_id, TaskErrorNo.E_COMMON_INVALID_VALUE)
            if scan_task_id is None:
                log.logger.error("XvsaDockerExecutor", "construct_scan_container_name",
                                "invalid scan_task_id, scan_task_id: %s" % scan_task_id)
                raise XcalException("XvsaDockerExecutor", "construct_scan_container_name", "invalid scan_task_id, scan_task_id: %s" % scan_task_id, TaskErrorNo.E_COMMON_INVALID_VALUE)

            container_name = "scan" + "_" + project_id + "_" + scan_task_id
            return container_name

    def execute_docker_scan(self, scan_properties: list, task_config: ConfigObject):
        with XcalLogger("XvsaEngineBootstrapper", "execute_docker_scan", parent=self.logger) as log:
            # Copy preprocess result to share-volume
            self.copy_to_share_volume()

            mem_limit = os.getenv("SCAN_DOCKER_MEM_LIMIT", SCAN_DOCKER_MEM_LIMIT)
            memswap_limit = os.getenv("SCAN_DOCKER_MEMSWAP_LIMIT")

            mem_limit = task_config.get("scanMemLimit", mem_limit)
            memswap_limit = task_config.get("scanMemSwapLimit", memswap_limit)

            # when mem swap is not set, disable the docker container use swap space
            if memswap_limit is None:
                memswap_limit = mem_limit

            remove_container = task_config.get("removeScanContainer", True)
            if isinstance(remove_container, str) and remove_container.lower() in ["n", "no"]:
                remove_container = False

            container_name = XvsaDockerExecutor.construct_scan_container_name(task_config)

            docker_utility = DockerUtility(log, container_name, os.getenv("SCAN_IMAGE"), os.getenv("SCAN_COMMAND"), os.getenv("DOCKER_NETWORK"), mem_limit = mem_limit, memswap_limit = memswap_limit, remove_container = remove_container)

            # Determine volumes to mount
            share_xvsa_volume = os.getenv("SHARE_XVSA_VOLUME")
            share_scan_volume = os.getenv("SHARE_SCAN_VOLUME")
            share_ws_app_volume = os.getenv("SHARE_WS_APP_VOLUME")

            if share_xvsa_volume is not None:
                docker_utility.volumes.append(share_xvsa_volume)
            if share_scan_volume is not None:
                docker_utility.volumes.append(share_scan_volume)
            if share_ws_app_volume is not None:
                docker_utility.volumes.append(share_ws_app_volume)

            # Environment Vars
            docker_utility.env_vars = scan_properties

            # Execute Run
            docker_utility.start_scan_container(task_config)

    @staticmethod
    def remove_container(task_config: ConfigObject): 
        container_name = XvsaDockerExecutor.construct_scan_container_name(task_config)    
        DockerUtility.remove_scan_container(container_name)

    def copy_to_share_volume(self):
        self.logger.trace("no-op copying to share volume", "copied nothing because shared volume does not need it")
        pass


# Initiate a XVSA scan
class XvsaEngineBootstrapper(object):
    def __init__(self, logger:XcalLogger):
        self.logger = logger

    def invoke_xvsa_via_queue(self, task_info: dict):
        JobInitiator(self.logger).initiate_job_flow(SCAN_ENGINE_TOPIC, task_info, expire_type = ExpireHookType.EXPIRE_IGNORE)
        pass

    def collect_performance_data(self, scan_work_dir):
        all_files_count = 0
        all_files_size = 0
        all_files_line_count = 0

        # Calculate file line count.
        try:
            file_info_file_local_path = os.path.join(scan_work_dir, FILE_INFO_FILE_NAME)
            with open(file_info_file_local_path, "r") as f:
                file_info_content = json.load(f)
                source_files = file_info_content.get("files", [])
                for source_file in source_files:
                    if source_file.get("type") is not None and (source_file.get("type") == "DIRECTORY"):
                        continue
                    file_line_count = int(source_file.get("noOfLines", 0))
                    file_size = int(source_file.get("fileSize", 0))
                    all_files_count += 1
                    all_files_size += file_size
                    all_files_line_count += file_line_count

                self.logger.trace("collect_performance_data", "source code info, src_size: %d, src_files_count: %d, src_files_lines: %d" %
                          (all_files_size, all_files_count, all_files_line_count))
                scanSourceFileSize.set(all_files_size)
                scanSourceFileLines.set(all_files_line_count)
                scanSourceFileCount.set(all_files_count)
        except Exception as err:
            logging.exception(err)
            # Continue without interruption, this is only a monitoring purpose action and should not stop the whole scan

        # TODO: Predicting system requirements...

    def execute_scan(self, task_config:ConfigObject):
        with XcalLogger(str(XvsaEngineBootstrapper.__class__.__name__), "execute_scan", parent=self.logger) as log:
            try:
                # Prepare Env Variables
                scan_task_id = task_config.get('scanTaskId')
                scan_work_dir = os.path.join(BASE_SCAN_PATH, scan_task_id)
                token_string = TokenExtractor(task_config).get_xvsa_token()
                api_server_name = ScanTaskServiceAPIData().xvsa_hostname

                self.collect_performance_data(scan_work_dir)

                # <---DEVONLY-IF--->
                # For internal use only, user specifiable XVSA options
                scan_extra_options = task_config.get("xvsaOptions", "")
                scan_extra_options += ' -VSA:magic=%s' % guid.next_id()
                # <---DEVONLY-END--->

                scan_mode = task_config.get("scanMode", "")
                parallel_jobs = task_config.get("parallelJobs", "")

                scan_properties = self.get_scan_properties(scan_task_id, scan_work_dir, token_string, api_server_name, scan_extra_options, scan_mode, parallel_jobs)

                log.trace("execute_scan", ("scan task id:", scan_task_id, "token :", token_string, "scan_path", scan_work_dir, "scan_properties", scan_properties))

                XvsaDockerExecutor(log).execute_docker_scan(scan_properties, task_config)
            except XcalException as err:
                # This log is used for Support & Debugging
                logging.exception(err)
                extra_msg = "scan container execute failed"  # Default message is applied when error is NOT exit in non-zero
                try:
                    proper_volume = os.getenv("SHARE_SCAN_VOLUME", "/share/scan:/share/scan")
                    volumes = proper_volume.split(":")
                    real_vol = volumes[0]
                    scan_path = scan_work_dir.replace("/share/scan", real_vol)
                except Exception as err:
                    logging.exception(err)

                if err.err_code == TaskErrorNo.E_DOCKER_CONATINER_EXITNZERO:
                    extra_msg = "xvsa = %d " % int(err.info.get("exit", "-9999"))
                    if int(err.info.get("exit", "9999")) == 20 + 30 + 11:
                        extra_msg = extra_msg + ", please renew or reimport your license"
                    elif int(err.info.get("exit", "9999")) == 20 + 30 + 9:
                        extra_msg = extra_msg + ", (Out of memory error), please try to increase your memory allowance"
                    elif int(err.info.get("exit", "9999")) < 30:
                        extra_msg = extra_msg + ", start.sh returned error, check logs"
                    elif int(err.info.get("exit", "9999")) < 50:
                        extra_msg = extra_msg + ", xvsa_scan returned error, check logs"
                    else:
                        extra_msg = "xvsa = %d, probably XVSA error occurred, please report to us with logs. " % int(err.info.get("exit", "-9999"))

                    raise XcalException("XvsaEngineBootstrapper", "execute_scan",
                                        "XvsaScan Exception, find scan.log in %s, %s" % (
                                            scan_path, extra_msg), TaskErrorNo.E_SRV_XVSA_EXECUTE_FAIL)
                else:
                    raise XcalException("XvsaEngineBootstrapper", "execute_scan",
                                        "XvsaScan failed cannot create docker container, workdir %s, %s, %s" % (
                                            scan_path, extra_msg, str(err.err_code)), TaskErrorNo.E_SRV_XVSA_DOCKER_FAIL)

    def get_scan_properties_from_task_config(self, task_config:ConfigObject):
        # Prepare Env Variables
        scan_task_id = task_config.get('scanTaskId')
        scan_work_dir = os.path.join(BASE_SCAN_PATH, scan_task_id)
        token_string = TokenExtractor(task_config).get_xvsa_token()
        api_server_name = ScanTaskServiceAPIData().xvsa_hostname

        self.collect_performance_data(scan_work_dir)

        # <---DEVONLY-IF--->
        # For internal use only, user specifiable XVSA options
        scan_extra_options = task_config.get("xvsaOptions", "")
        scan_extra_options += ' -VSA:magic=%s' % guid.next_id()
        # <---DEVONLY-END--->

        scan_mode = task_config.get("scanMode", "")
        parallel_jobs = task_config.get("parallelJobs", "")

        return self.get_scan_properties(scan_task_id, scan_work_dir, token_string, api_server_name, scan_extra_options, scan_mode, parallel_jobs)

    def get_scan_properties(self, scan_task_id, scan_work_dir, token_string, api_server_name, scan_extra_options, scan_mode, paralell_jobs):
        scan_properties = [
                     "SCAN_TASK_ID=%s" % scan_task_id,
                     "SCAN_DIR=%s" % scan_work_dir,
                     "SCAN_TOKEN=%s" % token_string,
                     "SCAN_SERVER=%s" % api_server_name,
                     "SCAN_MODE=%s" % scan_mode,
                     "PARALLEL_JOBS=%s" % paralell_jobs,
                     # <---DEVONLY-IF--->
                     "SCAN_EXTRA_OPTIONS=%s" % scan_extra_options,
                     # <---DEVONLY-END--->
                ]
        return scan_properties

    def post_scan_cleanup(self, task_config:ConfigObject):
        self.logger.info("No-op Post-scan cleanup ", "")
        pass

    def remove_scan_container(self,  task_config:ConfigObject):
        with XcalLogger(str(XvsaEngineBootstrapper.__class__.__name__), "execute_scan", parent=self.logger) as log:
            XvsaDockerExecutor(log).remove_container(task_config)