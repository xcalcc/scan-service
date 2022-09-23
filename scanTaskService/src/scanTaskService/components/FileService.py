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


import os
import subprocess
import tempfile
from enum import Enum

import hashlib

from common.XcalLogger import XcalLogger, XcalLoggerExternalLinker
from scanTaskService.Config import FILE_SERVICE_CONFIG, TaskErrorNo
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator
from common.ConfigObject import ConfigObject
from common.DownloadUtil import HashTracker, download, TrackerBase
from common.TokenExtractor import TokenExtractor
from common.XcalException import XcalException


class FileServiceType(Enum):
    SFTP = 1,
    HTTP = 2


class FileService(object):
    def __init__(self):
        pass

    def send_file(self, local_file_name, remote_dir):
        pass

    def fetch_file(self, remote_file_name, local_file_name):
        pass


# Below class not used yet #
class FileServiceImpl(FileService):
    def __init__(self, task_info:ConfigObject, logger:XcalLogger):
        super(FileServiceImpl).__init__()
        self.type = FileServiceType.SFTP
        self.logger = logger
        user_config = task_info.get("configContent")
        self.fs_info = ConfigObject({
            "sshUser":user_config.get("agentUser"),
            "sshServer": user_config.get("agentAddress"),
            "remoteNode": user_config.get("")
        })
        self.sent_list = []
        self.received_list = []
        return

    def send_file(self, local_file_name:str, remote_dir:str):
        base_name = os.path.basename(local_file_name)
        with XcalLogger("FileService", func_name = "sendFile", parent = self.logger) as logger:
            logger.info("invoke scp", ("scp %s %s@%s:%s" % (local_file_name, self.fs_info.get("sshUser"), self.fs_info.get("sshServer"), remote_dir)))

            # Run process while dumping log ---------------------
            with tempfile.TemporaryFile() as out_f:
                rc = subprocess.call("scp %s %s@%s:%s" % (local_file_name, self.fs_info.get("sshUser"), self.fs_info.get("sshServer"), remote_dir),
                                     stdout=out_f, stderr=subprocess.STDOUT, timeout=10000, shell=True)

                # Read output from tempfile ---------------------
                out_f.seek(0)  # Goto start
                buf = out_f.read()
                logger.info("scp finished, stdout", buf.decode("UTF-8"))  # Log the results
                if rc != 0:
                    raise XcalException("FileServiceImpl", "send_file", "failed due to scp fail %d" % rc,
                                        TaskErrorNo.E_SRV_FILE_SCP_SEND)

            logger.info("upload complete", "scp completed")
            robj = {"service": "sftp",
                "name": os.path.join(remote_dir, base_name),
                "result": rc,
                "status": "ok",
                "localFile": local_file_name,
                "fileName": base_name}
            self.sent_list.append(robj)
            return robj

    def fetch_file(self, remote_file_name, local_file_name):
        with XcalLogger('FileService', "fetch_file", self.logger) as log:
            log.info("fetchFile", "scp %s@%s:%s %s" % (self.fs_info.get("sshUser"), self.fs_info.get("sshServer"), remote_file_name, local_file_name))

            # Run process while dumping log ---------------------
            with tempfile.TemporaryFile() as out_f:
                rc = subprocess.call(
                    "scp %s@%s:%s %s" % (self.fs_info.get("sshUser"), self.fs_info.get("sshServer"),
                                         remote_file_name, local_file_name),
                    stdout=out_f, stderr=subprocess.STDOUT, shell=True)

                #  Read from beginning --------------------------
                out_f.seek(0)
                log.info("fetch_file", ("scp result = ", out_f.read().decode("UTF-8")))
                if rc != 0:
                    raise XcalException("FileServiceImpl", "fetch_file", "failed due to scp fail %d" % rc,
                                        TaskErrorNo.E_SRV_FILE_SCP_GET_FAIL)

            log.info("download complete", "scp completed")
            robj = {"service": "sftp",
                "name": remote_file_name,
                "result": rc,
                "status": "ok",
                "localFile": local_file_name,
                "fileName": remote_file_name}

            self.received_list.append(robj)
            return robj


class FileFetchTracker(TrackerBase):
    def __init__(self, logger:XcalLogger, task_config):
        self.progress = 1.0
        self.progress_delta = 0.1
        self.minimizing_coefficient = 0.9
        self.logger = logger
        self.comms = XcalInternalCommunicator(self.logger, task_config=task_config)
        self.task_config = task_config

    def on_start(self, response):
        """Called with requests.Response object, which has response headers"""
        self.progress = 2.0
        pass

    def on_chunk(self, chunk):
        """Called multiple times, with bytestrings of data received"""
        self.progress += self.progress_delta
        self.progress_delta *= self.minimizing_coefficient
        # self.comms.upload_progress(self.task_config.get("scanTaskId"), Stage.PREPROCESS, Status.PROCESSING,
        #                            int(80 + 0.2 * (self.progress)), "Preprocess result downloading...")
        pass

    def on_finish(self):
        """Called when the download has completed"""
        self.logger.info("Download file compelete under percent", (self.progress, self.progress_delta))
        self.progress = 100
        pass


class RemoteFileService(FileService):
    def __init__(self, task_info: ConfigObject, logger: XcalLogger):
        super(RemoteFileService).__init__()
        self.type = FileServiceType.HTTP
        self.logger = logger
        self.sent_list = []
        self.received_list = []
        return

    def fetch_file_with_token(self, file_id:str, local_file_name:str, task_info):
        with XcalLogger('FileService', "fetch_file_with_token", self.logger) as log:
            log.trace("fetch_file_with_token", "file name : %s" % file_id)

            local_file_dir = os.path.dirname(local_file_name)
            if not os.path.exists(local_file_dir):
                os.makedirs(local_file_dir)

            # assert file_id is not None, 'file id should not be None'
            download_path = FILE_SERVICE_CONFIG.get("schema") + \
                            FILE_SERVICE_CONFIG.get("serverAddress") + \
                            FILE_SERVICE_CONFIG.get("downloadApi") \
                            .replace(FILE_SERVICE_CONFIG.get("downloadFieldName"), file_id) + \
                FILE_SERVICE_CONFIG.get("extraParam").replace("{token}", TokenExtractor(task_info).get_plain_token())

            hasher = HashTracker(hashlib.sha256())
            progress = FileFetchTracker(log, task_info)

            headers = XcalLoggerExternalLinker.prepare_client_request_headers(download_path, "GET", log)

            download(download_path, local_file_name, headers = headers, trackers=(hasher, progress))

            log.trace("download complete %s -> %s" % (download_path, local_file_name), "file hash %s" % hasher.hashobj.hexdigest())
            robj = {"service": "http",
                    "result": 0,
                    "status": "ok",
                    "localFile": local_file_name,
                    "filename": file_id}

            self.received_list.append(robj)
            return robj