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


class ScanMetrics(object):
    @staticmethod
    def push_to_gateway(push_url, job, reg):
        try:
            from prometheus_client import push_to_gateway
            push_to_gateway(push_url, job, reg, timeout=1)
        except Exception as err:
            logging.debug("[FAILED] Prometheus is not working !!! push_to_gateway failed !!!", str(err))
            pass