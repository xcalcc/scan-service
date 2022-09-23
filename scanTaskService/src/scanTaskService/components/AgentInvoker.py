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


from common.CommonGlobals import VCS_DIFF_RESULT_FILE_NAME, PREPROCESS_FILE_NAME, FILE_INFO_FILE_NAME, \
    SOURCE_CODE_ARCHIVE_FILE_NAME, SOURCE_FILES_NAME
from common.XcalLogger import XcalLogger, XcalLoggerExternalLinker
from scanTaskService.Config import AGENT_NAME_DEFAULT, AGENT_TOPIC_PREFIX, TaskErrorNo, JOB_QUEUE_NAME, \
    SPOTBUGS_RESULT_V_FILE_TEMP_NAME, JAVA_RUNTIME_OBJECT_FILE_NAME, ENABLE_SPOTBUGS
from scanTaskService.XcalExpirationWatch import ExpireHookType
from scanTaskService.components.JobInitiator import JobInitiator
from common.ConfigObject import ConfigObject
from common.XcalException import XcalException


class AgentInvoker(object):
    def __init__(self, logger: XcalLogger):
        self.logger = logger

    def invoke_agent_via_queue(self, job_steps, task_info: ConfigObject):
        """
        Invoke agent via a queue (currently Kafka/In-Mem queue)
        :param job_steps:
        :param task_info:
        :return:
        """
        agent_name = task_info.get('agentName', AGENT_NAME_DEFAULT)
        job_queue_name = task_info.get("jobQueueName", JOB_QUEUE_NAME)  # Server side only send one job queue name

        job_config = {
            "agentName": agent_name,
            "steps": job_steps,
            "span": XcalLoggerExternalLinker.prepare_client_request_string("agent", "GET", self.logger),
            "taskConfig": task_info.convert_to_dict(),
            "newagent": "v2"    # Version Indicator
        }

        JobInitiator(self.logger).initiate_job_flow(AGENT_TOPIC_PREFIX + job_queue_name,
                                                    job_config,
                                                    expire_type = ExpireHookType.EXPIRE_CONNECT_AGENT)

    def prepare_steps(self, preprocess_location, task_info: ConfigObject):
        """
        Extract Information and Append to step list (both C/C++ or Java is here)
        :param preprocess_location: str
        :param task_info: ConfigObject
        :return: steps:list, the steps prepared that meant to be sent to agent, in
                  {"id": len(steps), "parent": 0, "type": "xxxScanStepTypexxxx"}
        """
        steps = []

        #      ------------------------------------------
        #
        #      Extract All Information
        #
        #      ------------------------------------------
        self.logger.debug("prepare_steps", "taskConfig: %s" % task_info)

        if preprocess_location is None:
            if task_info.get("workdir") is not None:
                preprocess_location = task_info.get("workdir")
            else:
                raise XcalException("AgentInvoker", "prepare_steps", "preprocess_location not found",
                                    TaskErrorNo.E_SRV_AGENT_NO_PREPROCESS_LOC)

        upload_source = task_info.get("uploadSource")

        if task_info.get("sourceCodeAddress") is not None:
            # source code url ------------------------------------------
            timeout = task_info.get("timeout", "1200")
            # Add Source Code Fetch Task
            steps.append({"id": len(steps), "parent": 0, "type": "getSourceCode",
                          "sourceCodeAddress": task_info.get("sourceCodeAddress"),
                          "vcsUsername": task_info.get("username"), "vcsToken": task_info.get("vcsToken"),
                          "branch": task_info.get("branch"), "ref": task_info.get("ref"), "timeout": timeout})

        # source_storage_name and source_storage_type is related to the fileStorage information in web service
        source_storage_name = task_info.get("sourceStorageName", "agent")
        source_storage_type = task_info.get("sourceStorageType", "agent")
        git_url = ""
        commit_id = task_info.get("commitId")
        baseline_commit_id = task_info.get("baselineCommitId")
        need_diff = True

        if (commit_id is None) or (baseline_commit_id is None) or (commit_id == baseline_commit_id):
            need_diff = False

        if source_storage_type.lower() in ["gitlab", "gitlab_v3", "github", "gerrit"]:
            git_url = self.get_not_none(task_info, "sourceCodeAddress")

        source_location = task_info.get("sourceCodePath", "/")
        self.logger.debug("User specified source Code location : " + source_location, "")

        #      ------------------------------------------
        #
        #      Prepare the steps list
        #
        #      ------------------------------------------

        if task_info.get("lang") == "java":
            # Java -> Plugin
            #java_command = task_info.get("build", task_info.get("buildCommand", "mvn"))
            java_command = task_info.get("build", "mvn")
            java_command_option = task_info.get("buildConfig", "")

            # Maven/Gradle Plugin invocation
            steps.append(
                {"id": len(steps), "parent": 0, "type": "java",                  "sourceStorageName": source_storage_name,
                 "workdir": preprocess_location, "outputDir": preprocess_location,
                 "buildMainDir": preprocess_location,
                 "buildCommand": java_command, "buildConfig": java_command_option})

            # get runtime object
            steps.append(
                {"id": len(steps), "parent": 0, "type":"runtimeObjectCollect",   "sourceStorageName": source_storage_name,
                 "workdir": preprocess_location, "outputDir": preprocess_location, "filename": JAVA_RUNTIME_OBJECT_FILE_NAME,
                 "name": "runtimeObjectCollect"})

            if ENABLE_SPOTBUGS or (isinstance(task_info.get("enableSpotbugs"), str) and task_info.get("enableSpotbugs").lower() in ["yes", "y", "true", "t"]):
                # Scanner Connector / Spotbugs
                steps.append(
                    {"id": len(steps), "parent": 0, "type": "scannerConnector",      "sourceStorageName": source_storage_name,
                     "workdir": preprocess_location, "outputDir": preprocess_location, "filename": SPOTBUGS_RESULT_V_FILE_TEMP_NAME,
                     "buildMainDir": preprocess_location,
                     "name": "scannerConnector"})
        else:
            # C/C++ -> XcalBuild
            # Prebuild (This is a back stage operation, not used right now)
            if task_info.get("prebuild") is not None:
                steps.append(
                    {"id": len(steps), "parent": 0, "type": "command",           "sourceStorageName": source_storage_name,
                     "workdir": preprocess_location,
                     "cmd": task_info.get("prebuild")})

            #build_cmd = task_info.get("build", task_info.get("buildCommand", "make"))
            build_cmd = task_info.get("builderPath", task_info.get("build", "make"))

            # Add XcalBuild Step
            xcalbuild_step = \
                {"id": len(steps), "parent": 0, "type": "xcalbuild",             "sourceStorageName": source_storage_name,
                 "buildMainDir": preprocess_location,
                 "buildCommand": build_cmd}

            # If configureCommand exists, add it to the xcalbuild_step
            if task_info.get('configureCommand') is not None:
                xcalbuild_step["configureCommand"] = task_info.get('configureCommand')

            # XcalBuild Preprocess -----------------------------
            steps.append(xcalbuild_step)

        # If user choose to upload source code on Agent Mode, add upload step
        if upload_source:
            timeout = task_info.get("timeout", "1200")
            steps.append(
                {"id": len(steps), "parent": 0, "type": "compressSourceCode",    "sourceStorageName": source_storage_name,
                          "sourceCodePath": task_info.get("sourceCodePath"),
                          "outputFileName": SOURCE_CODE_ARCHIVE_FILE_NAME, "inputFileName": SOURCE_FILES_NAME,
                          "timeout": timeout})
            steps.append(
                {"id": len(steps), "parent": 0, "type": "upload",               "sourceStorageName": source_storage_name,
                 "filename": SOURCE_CODE_ARCHIVE_FILE_NAME, "name": "sourceCode"})

        # Prepare FileInfo
        steps.append(
            {"id": len(steps), "parent": 0, "type": "prepareFileInfo",          "sourceStorageName": source_storage_name,
                      "sourceStorageType": source_storage_type, "uploadSource": upload_source,
                      "srcDir": source_location, "outputFileName": FILE_INFO_FILE_NAME, "inputFileName": SOURCE_FILES_NAME,
                      "gitUrl": git_url, "sourceCodeArchiveName": SOURCE_CODE_ARCHIVE_FILE_NAME})

        if need_diff:
            # Diff and get diff file
            steps.append({"id": len(steps), "parent": 0, "type": "diff", "sourceStorageName": source_storage_name,
                          "commitId": commit_id, "baselineCommitId": baseline_commit_id, "outputFileName": VCS_DIFF_RESULT_FILE_NAME})

        # Upload FileInfo
        steps.append({"id": len(steps), "parent": 0, "type": "upload",          "sourceStorageName": source_storage_name,
                      "filename": FILE_INFO_FILE_NAME, "name": "fileInfo"})

        # Upload Preprocess Results
        steps.append({"id": len(steps), "parent": 0, "type": "upload",          "sourceStorageName": source_storage_name,
                      "filename": PREPROCESS_FILE_NAME, "name": "preprocessResult"})

        if need_diff:
            # Upload diff file
            steps.append({"id": len(steps), "parent": 0, "type": "upload", "sourceStorageName": source_storage_name,
                          "filename": VCS_DIFF_RESULT_FILE_NAME, "name": "diffResult"})

        # Perform Cleanup
        steps.append({"id": len(steps), "parent": 0, "type": "sourceCleanup"})
        self.logger.debug("prepare_steps", "after prepare steps: %s" % steps)
        return steps

    def get_not_none(self, storage_obj, key):
        if storage_obj.get(key) is None:
            raise XcalException("AgentInvoker", "get_not_none", "key %s not found in task config" % key,
                                TaskErrorNo.E_SRV_AGENT_INVOKE_KEY_IN_CONFIG)
        return storage_obj.get(key)

    @staticmethod
    def extract_remote_file_id(task_info: ConfigObject, name: str):
        """
        Find an uploaded file id in tasks
        :param task_info: uploaded file's fileId on file-service,
        :param name: with given name (in upload task, see AgentInvoker.py)
        :return: None if no item matching the name is found
        """
        if task_info.get("uploadResults"):
            upload_results = task_info.get("uploadResults")
            for item in upload_results:
                if item.get("filename") == name:
                    return item.get("fileId")

        return None
