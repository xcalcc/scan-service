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

import requests
import json
import sys
try:
    r =requests.get("http://localhost/worker-health")
    print(r.text)
    worker_arr=json.loads(r.text)
    for worker in worker_arr:
        if worker["isAlive"]!="True":
            sys.exit(1)
    print("Health check done")
except Exception as e:
    print("error: {0}".format(e))
    sys.exit(1)