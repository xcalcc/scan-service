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
import time
import traceback

import docker
from common import ConfigObject
from common.CommonGlobals import Stage, Status, Percentage
from common.XcalLogger import XcalLogger
from common.XcalException import XcalException
from scanTaskService.Config import TaskErrorNo, SCAN_DOCKER_MEM_LIMIT
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator


class DockerUtility(object):
    def __init__(self, logger: XcalLogger, container_name: str, scan_image: str, command: str, network: str = None, mem_limit: str = SCAN_DOCKER_MEM_LIMIT,
                 memswap_limit: str = None, remove_container: bool = True):
        self.logger = logger
        self.container_name = container_name
        self.image = scan_image
        self.command = command
        self.network = network
        self.mem_limit = mem_limit
        self.memswap_limit = memswap_limit
        self.remove_container = remove_container

        self.env_vars = []
        self.volumes = []

    def __str__(self):
        return "container_name: %s, image: %s, command: %s, network: %s, mem_limit: %s, memswap_limit: %s, remove_container: %s" % (
            self.container_name, self.image, self.command, self.network, self.mem_limit, self.memswap_limit, self.remove_container)

    # will remove this when start_scan_container is ok
    def start_container(self):
        with XcalLogger("DockerUtility", "start_container", parent=self.logger) as log:
            try:
                client = docker.from_env()
                if self.mem_limit == self.memswap_limit:
                    log.trace("start_container", "not using swap space in scan docker container")
                container = client.containers.run(self.image, name = self.container_name, remove = True,
                                                  volumes = self.volumes,
                                                  environment = self.env_vars,
                                                  stdout = True, stderr = True,
                                                  network = self.network,
                                                  command = self.command,
                                                  mem_limit = self.mem_limit,
                                                  memswap_limit = self.memswap_limit,
                                                  detach = True)

                # This will block until docker container finish
                for line in container.logs(stream=True):
                    logging.info("[output] %s", line.strip())

                result = container.wait()
                log.trace("start_container", "container running result is %s" % result)
                if result.get('StatusCode') != 0:
                    raise XcalException("DockerUtility", "start_container",
                                        (self.image.replace(":", "-") + " abnormal exit"),
                                        TaskErrorNo.E_DOCKER_CONATINER_EXITNZERO,
                                        info = {"exit": result.get('StatusCode')})
            except docker.errors.ImageNotFound as e:
                logging.exception(e)
                raise XcalException("DockerUtility", "start_container ",
                                    (self.image.replace(":", "-") + " image does not exist", self.image, str(e)),
                                    TaskErrorNo.E_DOCKER_NOIMAGEFOUND)
            except docker.errors.APIError as e:
                logging.exception(e)
                raise XcalException("DockerUtility", "start_container ",
                                    (self.image.replace(":", "-") + " api-error", str(e)),
                                    TaskErrorNo.E_DOCKER_API_ERROR)

    def start_scan_container(self, task_config: ConfigObject, interval: int = 5):
        with XcalLogger("DockerUtility", "start_scan_container", parent=self.logger) as log:
            try:
                client = docker.from_env()
                if self.mem_limit == self.memswap_limit:
                    log.trace("start_scan_container", "not using swap space in scan docker container")

                log.trace("start_scan_container", "scan container info: %s" % self.__str__())
                log.debug("start_scan_container", "scan container env_vars: %s, volumes: %s" % (self.env_vars, self.volumes))
                try:
                    container = client.containers.get(container_id = self.container_name)
                    log.trace("start_scan_container", "container exist: %s " % self.container_name)
                except docker.errors.NotFound as e:
                    log.trace("start_scan_container", "container not exist, creating: %s " % self.container_name)
                    container = client.containers.run(self.image, name = self.container_name,
                                                    volumes = self.volumes,
                                                    environment = self.env_vars,
                                                    stdout = True, stderr = True,
                                                    network = self.network,
                                                    command = self.command,
                                                    mem_limit = self.mem_limit,
                                                    memswap_limit = self.memswap_limit,
                                                    detach = True)

                last_time = time.monotonic()
                comms = XcalInternalCommunicator(log, task_config)
                scan_id = task_config.get("scanTaskId")
                # This will block until docker container finish
                for line in container.logs(stream = True):
                    logging.log(XcalLogger.XCAL_TRACE_LEVEL, "[output] %s", line.strip())
                    current_time = time.monotonic()
                    if current_time > last_time + interval:
                        last_time = current_time
                        comms.upload_progress(scan_id, Stage.SCANNING, Status.PROCESSING, Percentage.MIDDLE, message = line.strip().decode("utf-8"))

                result = container.wait()
                
                log.trace("start_scan_container", "container running result is %s" % result)
                if result.get('StatusCode') != 0:
                    raise XcalException("DockerUtility", "start_scan_container",
                                        (self.image.replace(":", "-") + " abnormal exit"),
                                        TaskErrorNo.E_DOCKER_CONATINER_EXITNZERO,
                                        info = {"exit": result.get('StatusCode')})
            except docker.errors.ImageNotFound as e:
                logging.exception(e)
                raise XcalException("DockerUtility", "start_scan_container ",
                                    (self.image.replace(":", "-") + " image does not exist", self.image, str(e)),
                                    TaskErrorNo.E_DOCKER_NOIMAGEFOUND)
            except docker.errors.APIError as e:
                logging.exception(e)
                raise XcalException("DockerUtility", "start_scan_container ",
                                    (self.image.replace(":", "-") + " api-error", str(e)),
                                    TaskErrorNo.E_DOCKER_API_ERROR)

    @staticmethod
    def remove_scan_container(container_name):
        with XcalLogger("DockerUtility", "remove_scan_container") as log:
            try:        
                client = docker.from_env()
                container = client.containers.get(container_id = container_name)
                log.trace("remove_scan_container", "container exist: %s " % container_name)
                container.remove()
            except Exception as e:
                log.warn("DockerUtility.remove_scan_container", "container not exist: %s" % (container_name))