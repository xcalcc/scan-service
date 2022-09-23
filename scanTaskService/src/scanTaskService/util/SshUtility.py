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
import shlex
import subprocess

from common.XcalLogger import XcalLogger

SSH_LOG_DIR = "/share/scan"                 # SSH preprocess log directory -----

class SshUtility(object):
    @staticmethod
    def ssh_execute(command:str, remote_user:str, remote_address:str, timeout:float, logger:XcalLogger):
        with XcalLogger("SshUtility", "ssh_execute", parent=logger) as log:

            ssh_line = "ssh %s@%s %s" % (remote_user, remote_address, shlex.quote(command))
            out_fn = os.path.join(SSH_LOG_DIR, "xcal.preprocess.log")

            log.info("ssh execution command", ssh_line)
            log.info("saving dump to file", ("file name :", out_fn))

            with open(out_fn, "wb+") as out_f:
                rc = subprocess.call(ssh_line, stdout=out_f, stderr=subprocess.STDOUT, shell=True, timeout=timeout)
                out_f.seek(0)
                out_str = out_f.read().decode("UTF-8")
                if (len(out_str) > 300):
                    out_str = out_str[-300:]
                # ================================
                log.info("ssh invoke stdout", ("stdout = ", out_str))  # Log the results

            return rc
