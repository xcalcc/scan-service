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
import os
import shutil
import subprocess
import time
import datetime
import re

from enum import Enum

from common.CommonGlobals import BASE_SCAN_PATH, PREPROCESS_FILE_NAME, FILE_INFO_FILE_NAME, VCS_DIFF_RESULT_FILE_NAME, \
    SOURCE_FILES_NAME, Percentage, TaskErrorNo
from common.CompressionUtility import CompressionUtility
from common.ConfigObject import ConfigObject
from common.XcalException import XcalException
from common.XcalLogger import XcalLogger
from scanTaskService.Config import DESTINATION_DIR_SUFFIX, JAVA_SCAN_RUNTIME_LOCAL_TEMP_FILE_NAME, \
    JAVA_SCAN_OBJECT_FILE_DIR, SCAN_RESULT_CONVERTER, UPLOAD_VOLUME_PATH, PREPROCESS_DATA_BUCKET_NAME, \
    SCAN_RESULT_COMPARATER, FILE_SERVICE_URL
from scanTaskService.components.AgentInvoker import AgentInvoker
from scanTaskService.components.CachedFileStorage import CachedFileStorage
from scanTaskService.components.DiffService import DiffService
from scanTaskService.components.ErrorRecover import POST_STATUS, PROC, STATUS, ERROR_RECOVER
from scanTaskService.components.FileService import RemoteFileService
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator, Stage, Status
from scanTaskService.components.XvsaBootstapper import XvsaEngineBootstrapper, XvsaDockerExecutor
from scanTaskService.util.KafkaUtility import KafkaUtility
from scanTaskService.util.file_util import get_client, FileUtil


class ScanMode(Enum):
    SINGLE = '-single'
    CROSS = '-cross'
    SINGLE_XSCA = '-single-xsca'
    XSCA = '-xsca'


class ScanController:

    def __init__(self, logger: XcalLogger, task_config: ConfigObject):
        self.logger = logger
        self.task_config = task_config
        self.comms = XcalInternalCommunicator(self.logger, self.task_config)
        self.scan_task_id = self.task_config.get('scanTaskId')
        self.work_dir = os.path.join(BASE_SCAN_PATH, self.scan_task_id)
        if not os.path.exists(self.work_dir):
            os.mkdir(self.work_dir)
        self.scan_lang = self.task_config.get('lang', '')
        self.scan_mode = self.task_config.get('scanMode', '')
        self.scan_all = self.task_config.get('scanAll', '')
        self.ignore_header = self.task_config.get('fileBlacklist', '')
        self.execution_type = 2
        self.baseline_scan_task_id = ''
        self.baseline_work_dir = ''

        # filename unify
        self.xvsa_ntxt = 'scan_result/xvsa-xfa-dummy.ntxt'
        self.xvsa_ltxt = 'scan_result/xvsa-xfa-dummy.ltxt'
        self.xvsa_etxt = 'scan_result/xvsa-xfa-dummy.etxt'
        self.xvsa_ftxt = 'scan_result/xvsa-xfa-dummy.ftxt'
        self.xvsa_csf = 'scan_result/xvsa-xfa-dummy.csf'
        self.xvsa_log = '.scan_log/scan.log'
        self.preprocess_tgz = 'preprocess.tar.gz'
        self.src_file_json = 'source_files.json'
        self.engine_merge_output_files="xvsa-xfa-dummy.mtxt"
        self.vtxt_diff_output_files="xvsa-xfa-dummy.[nlef]txt"
        self.v2csf_output_files="xvsa-xfa-dummy.csf"
        self.file_info_output_files="N/A"
        self.up_csf_output_files="N/A"

        # stage info unify
        self.start_info = 'sp_start'
        self.fetch_gdf = 'fetch_git_diff_file'
        self.fetch_pref = 'fetch_preprocess_file'
        self.fetch_finfo = 'fetch_file_info_file'
        self.fetch_src_json = 'fetch_src_file_json'
        self.fetch_rt = 'fetch_runtime_object_file'
        self.init_engine_merge = 'initial_engine_merge'
        self.exec_engine_merge = 'execute_engine_merge'
        self.fini_engine_merge = 'finish_engine_merge'
        self.init_vtxtdiff = 'initial_vtxtdiff'
        self.exec_vtxtdiff = 'execute_vtxtdiff'
        self.fini_vtxtdiff = 'finish_vtxtdiff'
        self.exec_v2csf = 'execute_v2csf'
        self.merge_fileinfo = 'merge_fileinfo'
        self.upload_fileinfo = 'upload_fileinfo'
        self.up_csf = 'upload_csf_file'
        self.fini_scan = 'finish_scan'

        # stage error unify
        self.unexp_err = 'unexpected exception'
        self.scan_cancelled = 'scan cancelled'
        self.fetch_pref_err = 'fetch preprocess file failed'
        self.fetch_finfo_err = 'fetch file info file failed'
        self.fetch_rt_err = 'fetch runtime object failed'
        self.fetch_src_json_err = 'fetch source files json failed'
        self.invalid_scan_task_info = 'invalid scan task info'
        self.no_ntxt = 'ntxt_file_path not exists'
        self.no_ltxt = 'ltxt_file_path not exists'
        self.no_etxt = 'etxt_file_path not exists'
        self.no_ftxt = 'ftxt_file_path not exists'
        self.no_csf = 'csf file not exists'
        self.merge_fileinfo_err = 'merge fileinfo.json failed'
        self.upload_fileinfo_err = 'upload fileinfo.json failed'
        self.up_csf_err = 'upload csf file failed'
        self.no_preprocess_tgz = 'preprocess.tar.gz is not exist'
        self.no_fileinfo_json = 'fileinfo.json is not exist'
        self.no_sourcefileid = 'sourceCodeFileId is None'
        self.retry_limit = 'retry limit reached'

        self.default_status = "SUCC"
        self.exec_parameters = "args"
        self.if_cancel = False
        self.kafka_topic = "proc-done"
        self.post_proc_kafka_topic = "postproc-done"

        self.proc_phase = 'PROC'
        self.post_proc_phase = 'POSTPROC'

        # task config json key
        self.TASK_CONFIG_KEY_UPLOAD_SOURCE = "uploadSource"

    # TODO: need to improve writing scan task log later, currently when no error occurs, scan task log record
    #  useful info otherwise record simple info. In fact, when error occurs, useful info is more important.
    def sp_start(self):
        """
        Sub-phase of PROC, start do sub-phase job here.
        Sub-phase include: engine_merge, vtxtdiff, v2csf and upload csf to POSTPROC
        """
        try:
            ps = POST_STATUS(self.scan_task_id, self.exec_parameters, self.default_status, self.work_dir, self.if_cancel)
            
            self.sp_preparation()
            # sub-phase: engine_merge run xvsa, xsca and vtxt merge
            # check if the scan task need be canceled, if True, break process
            if ps.if_cancel_scan_task():
                ps.fini_status = STATUS.CANCEL.name
                KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))
                ps.scan_task_delete()
                raise XcalException(PROC.ENGINE_MERGE.name, self.start_info, self.scan_cancelled, -1)

            init_time = datetime.datetime.utcnow()
            try:
                ps.output_files = self.engine_merge_output_files
                ps.exec_parameters = ("%s" % (os.getenv("SCAN_COMMAND")))
                ps.init(PROC.ENGINE_MERGE.name, PROC.ENGINE_MERGE.value, init_time=init_time, extra_message=self.preprocess_tgz)
                ps.engine_scan_info = self.sp_engine_merge()
            except XcalException as e:
                ps.fini_status = STATUS.FAILED.name
                if isinstance(e.err_code, Enum):
                    ps.error_code = e.err_code.value
                else:
                    ps.error_code = e.err_code
                raise e
            except Exception:
                ps.fini_status = STATUS.FAILED.name
                raise XcalException(PROC.ENGINE_MERGE.name, self.start_info, self.unexp_err, -1)
            finally:
                # when xvsa scan out of swap space, retry it
                if ps.fini_status == STATUS.COND_SUCC.name:
                    self.sp_recover(PROC.ENGINE_MERGE.name)
                ps.fini(PROC.ENGINE_MERGE.name, PROC.ENGINE_MERGE.value, init_time=init_time)
                if ps.fini_status == STATUS.FAILED.name:
                    # post msg of PROC status to Kafka
                    KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))
                    # when scan task finished/failed, delete the record of scan task in local folder named .xcalscan
                    ps.scan_task_delete()

            # sub-phase: vtxtdiff
            # check if the scan task need be canceled, if True, break process
            if ps.if_cancel_scan_task():
                ps.fini_status = STATUS.CANCEL.name
                KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))
                ps.scan_task_delete()
                raise XcalException(PROC.VTXTDIFF.name, self.start_info, self.scan_cancelled, -1)

            init_time = datetime.datetime.utcnow()
            try:
                ps.output_files = self.vtxt_diff_output_files
                ps.engine_scan_info = ""
                ps.init(PROC.VTXTDIFF.name, PROC.VTXTDIFF.value, init_time=init_time)
                execute_param_array = self.sp_vtxtdiff()
                ps.exec_parameters = str(execute_param_array).replace(",", " ")
            except XcalException as e:
                ps.fini_status = STATUS.FAILED.name
                ps.exec_parameters = SCAN_RESULT_COMPARATER
                if isinstance(e.err_code, Enum):
                    ps.error_code = e.err_code.value
                else:
                    ps.error_code = e.err_code
                raise e
            except Exception:
                ps.fini_status = STATUS.FAILED.name
                ps.exec_parameters = SCAN_RESULT_COMPARATER
                raise XcalException(PROC.VTXTDIFF.name, self.start_info, self.unexp_err, -1)
            finally:
                ps.fini(PROC.VTXTDIFF.name, PROC.VTXTDIFF.value, init_time=init_time)
                if ps.fini_status == STATUS.FAILED.name:
                    KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))
                    ps.scan_task_delete()

            # sub-phase: v2csf
            # check if the scan task need be canceled, if True, break process
            if ps.if_cancel_scan_task():
                ps.fini_status = STATUS.CANCEL.name
                KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))
                ps.scan_task_delete()
                raise XcalException(PROC.V2CSF.name, self.start_info, self.scan_cancelled, -1)

            init_time = datetime.datetime.utcnow()
            try:
                ps.output_files = self.v2csf_output_files
                ps.engine_scan_info = ""
                ps.init(PROC.V2CSF.name, PROC.V2CSF.value, init_time=init_time)
                execute_param_array = self.sp_v2csf()
                ps.exec_parameters = str(execute_param_array).replace(",", " ")
            except XcalException as e:
                ps.fini_status = STATUS.FAILED.name
                ps.exec_parameters = SCAN_RESULT_CONVERTER
                if isinstance(e.err_code, Enum):
                    ps.error_code = e.err_code.value
                else:
                    ps.error_code = e.err_code
                raise e
            except Exception:
                ps.fini_status = STATUS.FAILED.name
                ps.exec_parameters = SCAN_RESULT_CONVERTER
                raise XcalException(PROC.V2CSF.name, self.start_info, self.unexp_err, -1)
            finally:
                ps.fini(PROC.V2CSF.name, PROC.V2CSF.value, init_time=init_time)
                if ps.fini_status == STATUS.FAILED.name:
                    KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))
                    ps.scan_task_delete()

            # sub-phase: fileinfo	
            # check if the scan task need be canceled, if True, break process	
            if ps.if_cancel_scan_task():	
                ps.fini_status = STATUS.CANCEL.name	
                KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))	
                ps.scan_task_delete()	
                raise XcalException(PROC.FILEINFO.name, self.start_info, self.scan_cancelled, -1)

            init_time = datetime.datetime.utcnow()
            try:	
                ps.exec_parameters = ""
                ps.engine_scan_info = ""
                ps.output_files = self.file_info_output_files
                ps.init(PROC.FILEINFO.name, PROC.FILEINFO.value, init_time=init_time)	
                self.sp_fileinfo()
            except XcalException as e:
                ps.fini_status = STATUS.FAILED.name
                if isinstance(e.err_code, Enum):
                    ps.error_code = e.err_code.value
                else:
                    ps.error_code = e.err_code
                raise e
            except Exception:	
                ps.fini_status = STATUS.FAILED.name	
                raise XcalException(PROC.FILEINFO.name, self.start_info, self.unexp_err, -1)	
            finally:	
                ps.fini(PROC.FILEINFO.name, PROC.FILEINFO.value, init_time=init_time)	
                if ps.fini_status == STATUS.FAILED.name:	
                    KafkaUtility.kafka_publish(self.kafka_topic,
                                               json.dumps(ps.post_kafka_msg(self.proc_phase), indent=1))
                    ps.scan_task_delete()	

            # sub-phase: upload csf to POSTPROC
            # check if the scan task need be canceled, if True, break process
            if ps.if_cancel_scan_task():
                ps.fini_status = STATUS.CANCEL.name
                self.comms.upload_progress(self.scan_task_id, Stage.IMPORT_RESULT, Status.TERMINATED, Percentage.END, 'Cancelled before POSTPROC' , TaskErrorNo.E_API_SCANTASK_TERMINATED_BY_USER)
                KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.post_proc_phase), indent=1))
                ps.scan_task_delete()
                raise XcalException(PROC.UP_CSF.name, self.start_info, self.scan_cancelled, -1)

            init_time = datetime.datetime.utcnow()
            try:
                
                ps.output_files = self.up_csf_output_files
                ps.engine_scan_info = ""
                execute_param_array = self.get_sp_upload_csf_params()
                ps.exec_parameters = str(execute_param_array).replace(",", " ")
                ps.init(PROC.UP_CSF.name, PROC.UP_CSF.value, init_time=init_time)
                self.sp_upload_csf()
            except XcalException as e:
                ps.fini_status = STATUS.FAILED.name
                if isinstance(e.err_code, Enum):
                    ps.error_code = e.err_code.value
                else:
                    ps.error_code = e.err_code
                raise e
            except Exception:
                ps.fini_status = STATUS.FAILED.name
                raise XcalException(PROC.UP_CSF.name, self.start_info, self.unexp_err, -1)
            finally:
                # when upload csf failed, retry it
                if ps.fini_status == STATUS.FAILED.name:
                    try:
                        self.sp_recover(PROC.UP_CSF.name)
                        ps.fini_status = STATUS.SUCC.name
                    except Exception:
                        # skip as it is already failed status
                        pass
                if ps.fini_status == STATUS.SUCC.name:
                    self.comms.upload_progress(self.scan_task_id, Stage.IMPORT_RESULT, Status.COMPLETED, Percentage.END, 'Success in POSTPROC', TaskErrorNo.SUCCESS)
                elif ps.fini_status == STATUS.FAILED:
                    self.comms.upload_progress(self.scan_task_id, Stage.IMPORT_RESULT, Status.FAIL, Percentage.END, 'Failed in POSTPROC', TaskErrorNo.E_IMPORT_RESULT_ALL_FAILED)
                ps.fini(PROC.UP_CSF.name, PROC.UP_CSF.value, init_time=init_time)
                KafkaUtility.kafka_publish(self.post_proc_kafka_topic, json.dumps(ps.post_kafka_msg(self.post_proc_phase), indent=1))
                ps.scan_task_delete()
        except XcalException as e:
            if ps.fini_status != STATUS.CANCEL.name:
                ps.fini_status = STATUS.FAILED.name
            KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.post_proc_phase), indent=1))
            raise e
        except Exception as e:
            ps.fini_status = STATUS.FAILED.name
            KafkaUtility.kafka_publish(self.kafka_topic, json.dumps(ps.post_kafka_msg(self.post_proc_phase), indent=1))
            raise e
        finally:
            XvsaDockerExecutor.remove_container(self.task_config)

    def sp_preparation(self):
        client = get_client(self.logger, FILE_SERVICE_URL)
        file_util = FileUtil(client, self.logger)
        bucket_name = PREPROCESS_DATA_BUCKET_NAME
        object_prefix_path = os.path.join(self.task_config.get("projectId"), self.scan_task_id)
        self.fetch_git_diff_file(object_prefix_path, bucket_name, file_util)
        self.fetch_preprocess_file(object_prefix_path, bucket_name, file_util)
        self.fetch_file_info_file(object_prefix_path, bucket_name, file_util)
        # self.fetch_src_file_json()
        self.fetch_runtime_object_file()

    def sp_engine_merge(self):
        self.initial_engine_merge()
        self.execute_engine_merge()
        scan_info = self.cleanup_engine_merge()
        return scan_info

    def sp_vtxtdiff(self):
        self.initial_vtxtdiff()
        exec_args = self.execute_vtxtdiff()
        self.cleanup_vtxtdiff()
        return exec_args

    def sp_v2csf(self):
        exec_args = self.execute_v2csf()
        return exec_args

    def sp_fileinfo(self):
        self.merge_file_info()
        self.upload_file_info_file()

    def get_sp_upload_csf_params(self):
        return self.get_upload_csf_file_params()

    def sp_upload_csf(self):
        self.upload_csf_file()
        self.finish_scan()

    def sp_recover_mem_check(self):
        signal_9 = "signal 9"
        out_swap = "out of swap space"
        scan_log = os.path.join(self.work_dir, self.xvsa_log)
        if not os.path.exists(scan_log):
            return False
        with open(scan_log, 'r') as xvsa_log:
            log_content = xvsa_log.readlines()
        for content in log_content:
            if signal_9 in content or out_swap in content:
                return True

    def sp_recover_runner(self, sub_phase: str):
        ps = POST_STATUS(self.scan_task_id, self.exec_parameters, self.default_status, self.work_dir, self.if_cancel)
        if sub_phase == PROC.ENGINE_MERGE.name:
            if self.sp_recover_mem_check():
                try:
                    self.sp_engine_merge()
                    ps.fini_status = STATUS.SUCC.name
                except Exception:
                    ps.fini_status = STATUS.FAILED.name
                    raise XcalException(PROC.ENGINE_MERGE.name, self.start_info, self.unexp_err, -1)
        if sub_phase == PROC.UP_CSF.name:
            try:
                self.sp_upload_csf()
                ps.fini_status = STATUS.SUCC.name
            except Exception:
                ps.fini_status = STATUS.FAILED.name
                raise XcalException(PROC.UP_CSF.name, self.start_info, self.unexp_err, -1)

    def sp_recover(self, sub_phase: str):
        ps = POST_STATUS(self.scan_task_id, self.exec_parameters, self.default_status, self.work_dir, self.if_cancel)
        err_recover = ERROR_RECOVER(sub_phase)

        retry_time = err_recover.retry_time()
        retry_timeout = err_recover.retry_timeout()
        retry_counter = 0
        while int(retry_counter) < int(retry_time):
            try:
                time.sleep(retry_timeout)
                ps.retry(sub_phase, retry_counter)
                self.sp_recover_runner(sub_phase)
                ps.fini_status = STATUS.SUCC.name
                # finish retry when successfully executed
                break
            except Exception:
                ps.fini_status = STATUS.FAILED.name
                retry_counter += 1
        if ps.fini_status == STATUS.SUCC.name:
            pass
        else:
            raise XcalException(PROC.UP_CSF.name, self.start_info, self.retry_limit, -1)

    def fetch_git_diff_file(self, object_prefix_path, bucket_name, file_util):
        with XcalLogger(PROC.ENGINE_MERGE.name, self.fetch_gdf, parent=self.logger) as log:
            log.trace(self.fetch_gdf, "get repo diff file")
            diff_result_file = os.path.join(object_prefix_path, VCS_DIFF_RESULT_FILE_NAME)
            if file_util.file_exists(bucket_name, diff_result_file):
                file_util.download_file(bucket_name, diff_result_file, os.path.join(self.work_dir, VCS_DIFF_RESULT_FILE_NAME))

    def fetch_preprocess_file(self, object_prefix_path, bucket_name, file_util):
        with XcalLogger(PROC.ENGINE_MERGE.name, self.fetch_pref, parent=self.logger) as log:
            log.trace(self.fetch_pref, "get preprocess file")
            preprocess_file = os.path.join(object_prefix_path, PREPROCESS_FILE_NAME)
            if not file_util.file_exists(bucket_name, preprocess_file):
                raise XcalException(PROC.ENGINE_MERGE.name, self.fetch_pref, self.fetch_pref_err, -1)

            preprocess_file_archive_temp_filename = os.path.join(self.work_dir, PREPROCESS_FILE_NAME)
            file_util.download_file(bucket_name, preprocess_file, preprocess_file_archive_temp_filename)

            scan_preprocess_file_dir_name = self.scan_task_id + DESTINATION_DIR_SUFFIX
            CompressionUtility.extract_file(
                log,
                preprocess_file_archive_temp_filename,
                os.path.join(self.work_dir, scan_preprocess_file_dir_name),
                remove=False
            )

    def fetch_file_info_file(self, object_prefix_path, bucket_name, file_util):
        # file info is optional, so skip this if any exception occur
        with XcalLogger(PROC.ENGINE_MERGE.name, self.fetch_finfo, parent=self.logger) as log:
            try:
                log.trace(self.fetch_finfo, "get file info file")
                fileinfo_file = os.path.join(object_prefix_path, FILE_INFO_FILE_NAME)
                if not file_util.file_exists(bucket_name, fileinfo_file):
                    raise XcalException(PROC.ENGINE_MERGE.name, self.fetch_finfo, self.fetch_finfo_err, -1)

                file_util.download_file(bucket_name, fileinfo_file, os.path.join(self.work_dir, FILE_INFO_FILE_NAME))
            except Exception as e:
                log.warn(self.fetch_file_info_file, "failed to fetch file info : %s" % str(e))

    # TODO: temporarily not used, need to use new file service implementation if needed
    def fetch_src_file_json(self):
        with XcalLogger(PROC.ENGINE_MERGE.name, self.fetch_src_json, parent=self.logger) as log:
            src_file_json_id = AgentInvoker.extract_remote_file_id(self.task_config, SOURCE_FILES_NAME)
            if src_file_json_id is None:
                log.error(PROC.ENGINE_MERGE.name, self.fetch_src_json, self.fetch_src_json_err)
                raise XcalException(PROC.ENGINE_MERGE.name, self.fetch_src_json, self.fetch_src_json_err, -1)

            src_file_json = os.path.join(self.work_dir, SOURCE_FILES_NAME)
            RemoteFileService(self.task_config, log).fetch_file_with_token(
                src_file_json_id,
                src_file_json,
                self.task_config
            )

    # TODO: when scan java projects, need to use new file service implementation
    def fetch_runtime_object_file(self):
        with XcalLogger(PROC.ENGINE_MERGE.name, self.fetch_rt, parent=self.logger) as log:
            if self.scan_lang == 'java':
                cache = CachedFileStorage(log, self.task_config)
                checksum = self.task_config.get('runtimeLibraryChecksum')

                runtime_cache_setting_value = cache.check_storage_exists(checksum)
                if runtime_cache_setting_value is None:
                    log.warn(PROC.ENGINE_MERGE.name, 'no caching file related to checksum %s found' % checksum)
                    raise XcalException(PROC.ENGINE_MERGE.name, self.fetch_rt, self.fetch_rt_err, -1)

                artifact_file_id = runtime_cache_setting_value.get('artifactFileId')
                file_id = runtime_cache_setting_value.get('fileId')

                local_runtime_file_package = os.path.join(self.work_dir, JAVA_SCAN_RUNTIME_LOCAL_TEMP_FILE_NAME)
                dest_path = self.work_dir
                if artifact_file_id is not None:
                    RemoteFileService(self.task_config, log).fetch_file_with_token(
                        artifact_file_id,
                        local_runtime_file_package,
                        self.task_config
                    )
                elif file_id is not None:
                    RemoteFileService(self.task_config, log).fetch_file_with_token(
                        file_id,
                        local_runtime_file_package,
                        self.task_config
                    )
                    dest_path = os.path.join(dest_path, JAVA_SCAN_OBJECT_FILE_DIR)
                else:
                    log.warn(PROC.ENGINE_MERGE.name, self.fetch_rt_err)
                    raise XcalException(PROC.ENGINE_MERGE.name, self.fetch_rt, self.fetch_rt_err, -1)

                if not os.path.exists(local_runtime_file_package):
                    log.error(PROC.ENGINE_MERGE.name, self.fetch_rt, self.fetch_rt_err)
                    raise XcalException(PROC.ENGINE_MERGE.name, self.fetch_rt, self.fetch_rt_err, -1)

                CompressionUtility.extract_file(
                    log,
                    local_runtime_file_package,
                    dest_path,
                    remove=True
                )

    def initial_engine_merge(self):
        with XcalLogger(PROC.ENGINE_MERGE.name, self.init_engine_merge, parent=self.logger) as log:
            pass

    def execute_engine_merge(self):
        with XcalLogger(PROC.ENGINE_MERGE.name, self.exec_engine_merge, parent=self.logger) as log:
            if self.execution_type == 1:
                XvsaEngineBootstrapper(log).invoke_xvsa_via_queue(self.task_config.convert_to_dict())
            elif self.execution_type == 2:
                XvsaEngineBootstrapper(log).execute_scan(self.task_config)
                XvsaEngineBootstrapper(log).post_scan_cleanup(self.task_config)
            else:
                log.error(PROC.ENGINE_MERGE.name, self.exec_engine_merge, self.unexp_err)
                raise XcalException(PROC.ENGINE_MERGE.name, self.exec_engine_merge, self.unexp_err, -1)

    def cleanup_engine_merge(self):
        i_file_num = "FILE_I_NUM is"
        ii_file_num = "FILE_II_NUM is"
        xvsa_cross_time = "XVSA_CROSS_SCAN time usage"
        xvsa_single_time = "XVSA_SINGLE_SCAN time usage"
        xsca_single_time = "XSCA_SINGLE_SCAN time usage"
        vtxt_merge_time = "VTXTMERGE time usage"

        scan_info = ""
        log_content = ""
        scan_log = os.path.join(self.work_dir, self.xvsa_log)
        if not os.path.exists(scan_log):
            return scan_info
        with open(scan_log, 'r') as xvsa_log:
            try:
                log_content = xvsa_log.readlines()
            # when reading scan.log, it has non-standard format in 'utf-8' and 'unicode_escape', pass it first avoid fail
            except UnicodeDecodeError:
                scan_info = "Decode Error when reading scan.log, pass it first."
                pass
        for content in log_content:
            i_num = re.search(r'%s (.*)' % i_file_num, content)
            ii_num = re.search(r'%s (.*)' % ii_file_num, content)
            xvsa_crs_time = re.search(r'%s: (.*)' % xvsa_cross_time, content)
            xvsa_sgl_time = re.search(r'%s: (.*)' % xvsa_single_time, content)
            xsca_sgl_time = re.search(r'%s: (.*)' % xsca_single_time, content)
            vtxt_merg_time = re.search(r'%s: (.*)' % vtxt_merge_time, content)
            if i_num:
                scan_info += "i-file-num:%s " % i_num.group(1)
            if ii_num:
                scan_info += "ii-file-num:%s " % ii_num.group(1)
            if xvsa_crs_time:
                scan_info += "xvsa-cross-scan-time:%s " % xvsa_crs_time.group(1)
            if xvsa_sgl_time:
                scan_info += "xvsa-single-scan-time:%s " % xvsa_sgl_time.group(1)
            if xsca_sgl_time:
                scan_info += "xsca-single-scan-time:%s " % xsca_sgl_time.group(1)
            if vtxt_merg_time:
                scan_info += "vtxt-merge-time:%s " % vtxt_merg_time.group(1)
        return scan_info

    def initial_vtxtdiff(self):
        with XcalLogger(PROC.VTXTDIFF.name, self.init_vtxtdiff, parent=self.logger) as log:
            pass

    def execute_vtxtdiff(self):
        with XcalLogger(PROC.VTXTDIFF.name, self.exec_vtxtdiff, parent=self.logger) as log:
            scan_task_info = self.comms.search_scan_task()
            if scan_task_info is None:
                log.error(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.invalid_scan_task_info)
                raise XcalException(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.invalid_scan_task_info, -1)

            partial_scan = True
            ntxt_file_path, ltxt_file_path, etxt_file_path, ftxt_file_path = '', '', '', ''
            baseline_project_path = None
            if len(scan_task_info.json().get('content')) > 0:
                baseline_project_path = scan_task_info.json().get('content')[0].get('sourceRoot')
                log.trace(PROC.VTXTDIFF.name, 'baseline_project_path: %s' % baseline_project_path)
                if baseline_project_path is None:
                    raise XcalException(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.invalid_scan_task_info, -1)
                self.baseline_scan_task_id = scan_task_info.json().get('content')[0].get('id')
                if self.baseline_scan_task_id is not None:
                    self.baseline_work_dir = os.path.join(BASE_SCAN_PATH, self.baseline_scan_task_id)

                    ntxt_file_path = os.path.join(self.baseline_work_dir, self.xvsa_ntxt)
                    log.trace(PROC.VTXTDIFF.name, 'ntxt_file_path: %s' % ntxt_file_path)
                    if not os.path.exists(ntxt_file_path):
                        log.error(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_ntxt)
                        raise XcalException(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_ntxt, -1)

                    ltxt_file_path = os.path.join(self.baseline_work_dir, self.xvsa_ltxt)
                    log.trace(PROC.VTXTDIFF.name, 'ltxt_file_path: %s' % ltxt_file_path)
                    if not os.path.exists(ltxt_file_path):
                        log.error(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_ltxt)
                        raise XcalException(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_ltxt, -1)

                    etxt_file_path = os.path.join(self.baseline_work_dir, self.xvsa_etxt)
                    log.trace(PROC.VTXTDIFF.name, 'etxt_file_path: %s' % etxt_file_path)
                    if not os.path.exists(etxt_file_path):
                        log.error(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_etxt)
                        raise XcalException(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_etxt, -1)

                    ftxt_file_path = os.path.join(self.baseline_work_dir, self.xvsa_ftxt)
                    log.trace(PROC.VTXTDIFF.name, 'ftxt_file_path: %s' % ftxt_file_path)
                    if not os.path.exists(ftxt_file_path):
                        log.error(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_ftxt)
                        raise XcalException(PROC.VTXTDIFF.name, self.exec_vtxtdiff, self.no_ftxt, -1)

            # use xsca without dsr
            if self.scan_mode == ScanMode.SINGLE_XSCA.name:
                ntxt_file_path, ltxt_file_path, etxt_file_path, ftxt_file_path = '', '', '', ''
            # if user specify cleanCommand, it will not trigger Partial scan. Default is Partial scan now.
            if self.scan_all:
                partial_scan = False

            current_project_path = self.task_config.get('sourceCodePath')
            log.trace(PROC.VTXTDIFF.name, 'current_project_path: %s' % current_project_path)

            exec_args = DiffService(
                log,
                os.path.join(self.work_dir, VCS_DIFF_RESULT_FILE_NAME),
                ntxt_file_path,
                ltxt_file_path,
                etxt_file_path,
                ftxt_file_path,
                self.work_dir,
                partial_scan
            ).diff_scan_result(baseline_project_path, current_project_path)

            return exec_args

    def cleanup_vtxtdiff(self):
        with XcalLogger(PROC.VTXTDIFF.name, self.fini_vtxtdiff, parent=self.logger) as log:
            pass

    def execute_v2csf(self):
        with XcalLogger(PROC.V2CSF.name, self.exec_v2csf, parent=self.logger) as log:
            if not os.path.exists(SCAN_RESULT_CONVERTER):
                log.error(PROC.V2CSF.name, self.exec_v2csf, '%s not exists' % SCAN_RESULT_CONVERTER)
                raise XcalException(PROC.V2CSF.name, self.exec_v2csf, '%s not exists' % SCAN_RESULT_CONVERTER, -1)

            ntxt_file_path = os.path.join(self.work_dir, self.xvsa_ntxt)
            log.trace(PROC.V2CSF.name, 'ntxt_file_path: %s' % ntxt_file_path)
            if not os.path.exists(ntxt_file_path):
                log.error(PROC.V2CSF.name, self.exec_v2csf, self.no_ntxt)
                raise XcalException(PROC.V2CSF.name, self.exec_v2csf, self.no_ntxt, -1)

            ltxt_file_path = os.path.join(self.work_dir, self.xvsa_ltxt)
            log.trace(PROC.V2CSF.name, 'ltxt_file_path: %s' % ltxt_file_path)
            if not os.path.exists(ltxt_file_path):
                log.error(PROC.V2CSF.name, self.exec_v2csf, self.no_ltxt)
                raise XcalException(PROC.V2CSF.name, self.exec_v2csf, self.no_ltxt, -1)

            etxt_file_path = os.path.join(self.work_dir, self.xvsa_etxt)
            log.trace(PROC.V2CSF.name, 'etxt_file_path: %s' % etxt_file_path)
            if not os.path.exists(etxt_file_path):
                log.error(PROC.V2CSF.name, self.exec_v2csf, self.no_etxt)
                raise XcalException(PROC.V2CSF.name, self.exec_v2csf, self.no_etxt, -1)

            ftxt_file_path = os.path.join(self.work_dir, self.xvsa_ftxt)
            log.trace(PROC.V2CSF.name, 'ftxt_file_path: %s' % ftxt_file_path)
            if not os.path.exists(ftxt_file_path):
                log.error(PROC.V2CSF.name, self.exec_v2csf, self.no_ftxt)
                raise XcalException(PROC.V2CSF.name, self.exec_v2csf, self.no_ftxt, -1)

            host_path = self.task_config.get('sourceCodePath')
            target_path = self.task_config.get('preprocessPath')

            params = [SCAN_RESULT_CONVERTER]
            if host_path is not None and len(host_path) > 0:
                params.extend(['-h', host_path])
            if target_path is not None and len(target_path) > 0:
                params.extend(['-t', target_path])

            params.extend(['-n', ntxt_file_path, '-l', ltxt_file_path, '-e', etxt_file_path, '-f', ftxt_file_path])
            # when user config the header files in black file list, turn on the ignore header file issues in v2csf
            if re.search(r'\.h', self.ignore_header):
                params.extend(['-i'])

            log.trace(self.exec_v2csf, ' '.join(params))
            try:
                st = time.time()
                p = subprocess.run(params, stdout=subprocess.PIPE, stderr = subprocess.PIPE, timeout=5400)
                et = time.time()
                log.trace(PROC.V2CSF.name, 'execute %s time: %f' % (SCAN_RESULT_CONVERTER, et - st))
                output = p.stdout.decode().split('\n')
                if len(output) > 1:
                    log.trace(PROC.V2CSF.name, output[-2])
            except subprocess.TimeoutExpired:
                msg = 'execute %s timeout' % SCAN_RESULT_CONVERTER
                log.error(PROC.V2CSF.name, self.exec_v2csf, msg)
                raise XcalException(PROC.V2CSF.name, self.exec_v2csf, msg, -1)

            if p.returncode != 0:
                msg = 'execute %s failed, exit(%d)' % (SCAN_RESULT_CONVERTER, p.returncode)
                log.error(PROC.V2CSF.name, self.exec_v2csf, msg)
                log.trace(PROC.V2CSF.name, 'stdout raw message: %s' % p.stdout)
                log.trace(PROC.V2CSF.name, 'stderr raw message: %s' % p.stderr)
                raise XcalException(PROC.V2CSF.name, self.exec_v2csf, msg, -1)

            return params

    def merge_file_info(self):
        with XcalLogger(PROC.FILEINFO.name, self.merge_fileinfo, parent=self.logger) as log:
            try:
                if len(self.baseline_scan_task_id) == 0:
                    log.trace(PROC.FILEINFO.name, 'no need merge fileinfo.json')
                    return

                last_file_info_file = os.path.join(self.baseline_work_dir, FILE_INFO_FILE_NAME)
                curr_file_info_file = os.path.join(self.work_dir, FILE_INFO_FILE_NAME)
                if not os.path.exists(last_file_info_file) or not os.path.exists(curr_file_info_file):
                    log.trace(PROC.FILEINFO.name, 'no need merge fileinfo.json')
                    return

                with open(last_file_info_file, 'r') as f:
                    last_file_info = json.load(f)
                with open(curr_file_info_file, 'r') as f:
                    curr_file_info = json.load(f)

                files = last_file_info['files']
                file_info_dict = {}
                for info in files:
                    file_info_dict[info['relativePath']] = info

                last_file_id = len(file_info_dict)

                new_files_num, new_dirs_num, line_count_diff = 0, 0, 0
                for info in curr_file_info['files']:
                    # TODO: CI/CD push/merge project root path is different and
                    #  we treat the project root path's relativePath as '/' in fileinfo,
                    #  may modify this later since it is not used right now.
                    if info['relativePath'] not in file_info_dict:  # if not exist in baseline
                        info['fileId'] = last_file_id
                        last_file_id += 1
                        files.append(info)
                        if info['type'] == 'FILE':
                            new_files_num += 1
                        elif info['type'] == 'DIRECTORY':
                            new_dirs_num += 1
                        line_count_diff += int(info['noOfLines'])
                    else:
                        # already exist in baseline
                        # update its info(version, checksum, fileSize and noOflines) to latest
                        last_info = file_info_dict[info['relativePath']]
                        line_count_diff -= int(last_info['noOfLines'])
                        line_count_diff += int(info['noOfLines'])
                        last_info['version'] = info.get('version')
                        last_info['checksum'] = info.get('checksum')
                        last_info['fileSize'] = info.get('fileSize')
                        last_info['noOfLines'] = info.get('noOfLines')

                # when sourceType is scm type, the value of file version is commit id.
                # update all files' version to current commit id since web main will use this info to get file content
                if last_file_info.get('sourceType').lower() in ["gitlab", "gitlab_v3", "github", "gerrit"]:
                    new_version = curr_file_info.get('files')[0].get('version')
                    for file in files:
                        file['version'] = new_version

                log.trace(PROC.FILEINFO.name, 'baseline total directories: %d new directories: %d' % (int(last_file_info['numberOfDirs']), new_dirs_num))
                log.trace(PROC.FILEINFO.name, 'baseline total files: %d new files: %d' % (int(last_file_info['numberOfFiles']), new_files_num))
                log.trace(PROC.FILEINFO.name, 'baseline total lines: %d lines increased/reduced: %d' % (int(last_file_info['totalLineNum']) , line_count_diff))

                last_file_info['sourceCodeFileId'] = curr_file_info['sourceCodeFileId']
                last_file_info['numberOfFiles'] = '%d' % (int(last_file_info['numberOfFiles']) + new_files_num)
                last_file_info['numberOfDirs'] = '%d' % (int(last_file_info['numberOfDirs']) + new_dirs_num)
                last_file_info['totalLineNum'] = '%d' % (int(last_file_info['totalLineNum']) + line_count_diff)

                os.rename(curr_file_info_file, '%s.bak' % curr_file_info_file)
                with open(curr_file_info_file, 'w') as f:
                    json.dump(last_file_info, f)
            except Exception as e:
                log.warn(self.merge_fileinfo, str(e))

    def upload_file_info_file(self):
        # upload file info is optional for the flow, so skip it when exceptions occur
        with XcalLogger(PROC.FILEINFO.name, self.upload_fileinfo, parent=self.logger) as log:
            try:
                if len(self.baseline_scan_task_id) == 0:
                    log.trace(PROC.FILEINFO.name, 'no need upload fileinfo.json')
                    return
                file_info_file_path = os.path.join(self.work_dir, FILE_INFO_FILE_NAME)
                if not os.path.exists(file_info_file_path):
                    log.warn(self.upload_fileinfo, self.no_fileinfo_json)
                else:
                    pass
                    # TODO: need to use new file service implementation
                    # shutil.move(file_info_file_path, os.path.join(file_root_path, FILE_INFO_FILE_NAME))
            except Exception as e:
                log.warn(self.upload_fileinfo, str(e))

    def get_upload_csf_file_params(self):
        return self.comms.get_upload_scan_result_params(self.scan_task_id, self.work_dir)

    def upload_csf_file(self):
        with XcalLogger(PROC.UP_CSF.name, self.up_csf, parent=self.logger) as log:
            csf_file_path = os.path.join(self.work_dir, self.xvsa_csf)
            if not os.path.exists(csf_file_path):
                log.error(PROC.UP_CSF.name, self.up_csf, self.no_csf)
                raise XcalException(PROC.UP_CSF.name, self.up_csf, self.no_csf, -1)

            try:
                self.comms.upload_scan_result(self.scan_task_id, self.work_dir)
            except Exception:
                raise XcalException(PROC.UP_CSF.name, self.up_csf, self.up_csf_err, -1)

    def finish_scan(self):
        # When finished scan and v2csf, delete useless preprocess.tar.gz to reduce disk usage.
        preprocess_tgz = os.path.join(self.work_dir, self.preprocess_tgz)
        if os.path.exists(preprocess_tgz):
            os.remove(preprocess_tgz)
        with XcalLogger(PROC.UP_CSF.name, self.fini_scan, parent=self.logger) as log:
            pass
