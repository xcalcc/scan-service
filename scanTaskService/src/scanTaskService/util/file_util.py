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
import time
from datetime import datetime

import certifi
import urllib3
from common.XcalException import XcalException
from common.XcalLogger import XcalLogger
from minio import Minio
from minio.commonconfig import ENABLED, Filter, Tags, CopySource
from minio.error import MinioException
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration

# Below info will be used in policy later
FILE_SERVICE_ACCESS_KEY = os.getenv("FILE_SERVICE_ACCESS_KEY", "AdminFileService")
FILE_SERVICE_SECRET_KEY = os.getenv("FILE_SERVICE_SECRET_KEY", "AdminFileService")
EXPIRED_DAY = os.getenv("EXPIRED_DAY", 7)
PREPROCESS_DATA_BUCKET_NAME = os.getenv("PREPROCESS_DATA_BUCKET_NAME", "preprocess-data")
OBJECT_TAGS_KEY = os.getenv("OBJECT_TAGS_KEY", "source")
OBJECT_TAGS_VALUE = os.getenv("OBJECT_TAGS_VALUE", "client")


def get_client(logger: XcalLogger, url: str, access_key: str = FILE_SERVICE_ACCESS_KEY, secret_key: str = FILE_SERVICE_SECRET_KEY):
    logger.info("get_client", "get file service client")

    urllib3.PoolManager.BACKOFF_MAX = 10
    http_client = urllib3.PoolManager(
        timeout = 30,
        cert_reqs = 'CERT_REQUIRED',
        ca_certs = certifi.where(),
        retries = urllib3.Retry(
            total = 3,
            backoff_factor = 10,
            status_forcelist = [500, 502, 503, 504]
        )
    )

    url = url.replace("http://", "")
    logger.debug("get_client", "file server url: %s" % url)

    try:
        client = Minio(url, access_key = access_key, secret_key = secret_key, secure = False, http_client = http_client)
    except MinioException as err:
        logger.exception(err)
        raise XcalException("FileUtil", "get_client", message = "connect to file service failed", err_code = -1)
    return client


class FileUtil(object):
    def __init__(self, client, logger: XcalLogger):
        self.client = client
        self.tags = Tags.new_object_tags()
        self.tags[OBJECT_TAGS_KEY] = OBJECT_TAGS_VALUE
        self.logger = logger

    def create_bucket(self, bucket_name):
        self.logger.debug("create_bucket", "create %s bucket in file service" % bucket_name)
        config = LifecycleConfig(
            [
                Rule(
                    ENABLED,
                    rule_filter = Filter(tag = self.tags),
                    rule_id = "rule1",
                    expiration = Expiration(days = int(EXPIRED_DAY)),
                ),
            ],
        )
        if not self.client.bucket_exists(bucket_name):
            try:
                self.client.make_bucket(bucket_name)
                self.client.set_bucket_lifecycle(bucket_name, config)
            except MinioException as err:
                self.logger.exception(err)
                raise XcalException("FileUtil", "create_bucket",
                                    message = "create bucket failed",
                                    err_code = -1)

    def upload_file(self, bucket_name, object_name, file_path):
        self.logger.debug("upload_file", "bucket: %s" % bucket_name)
        try:
            self.logger.info("upload_file", "upload file: %s, start time: %s" % (file_path, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
            self.client.fput_object(bucket_name, object_name, file_path, tags = self.tags)
            self.logger.info("upload_file", "upload file: %s, end time: %s" % (file_path, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
        except MinioException as err:
            self.logger.exception(err)
            raise XcalException("FileUtil", "upload_file", message="upload file failed", err_code = -1)

    def file_exists(self, bucket_name, object_name):
        self.logger.debug("file_exists", "bucket: %s, object: %s" % (bucket_name, object_name))
        try:
            self.client.stat_object(bucket_name, object_name)
            found = True
        except MinioException as err:
            self.logger.debug("file_exists", "object: %s does not exist" % object_name)
            found = False
        return found

    def download_file(self, bucket_name, object_name, file_path):
        self.logger.info("download_file", "bucket: %s, object_name: %s, file_path: %s" % (bucket_name, object_name, file_path))
        try:
            self.logger.info("download_file", "download file: %s, start time: %s" % (object_name, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
            self.client.fget_object(bucket_name, object_name, file_path)
            self.logger.info("download_file", "download file: %s, end time: %s" % (object_name, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
        except MinioException as err:
            self.logger.exception(err)
            raise XcalException("FileUtil", "download_file", message = "download file railed", err_code = -1)

    def move_object(self, source_bucket_name, source_object_name, dest_bucket_name, dest_object_name):
        self.logger.debug("move_object", "move object %s from bucket %s to %s in bucket %s" % (source_object_name, source_bucket_name, dest_object_name, dest_bucket_name))
        try:
            self.logger.info("move_object", "copy object: %s, start time: %s" % (source_object_name, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
            self.client.copy_object(dest_bucket_name, dest_object_name, CopySource(source_bucket_name, source_object_name))
            self.logger.info("move_object", "copy object: %s, end time: %s" % (source_object_name, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
            self.logger.info("move_object", "remove source object: %s, start time: %s" % (source_object_name, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
            self.client.remove_object(source_bucket_name, source_object_name)
            self.logger.info("move_object", "remove source object: %s, end time: %s" % (source_object_name, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S")))
        except MinioException as err:
            self.logger.exception(err)
            raise XcalException("FileUtil", "move_file", message = "move file railed", err_code = -1)



