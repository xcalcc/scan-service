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



import unittest

from common import VersionUtils


class TestVersionUtils(unittest.TestCase):
    def test_comparator(self):
        assert VersionUtils.VersionComparer.version_str_compare("1", "1") == 0
        assert VersionUtils.VersionComparer.version_str_compare("2.1", "2.2") < 0
        assert VersionUtils.VersionComparer.version_str_compare("3.0.4.10", "3.0.4.2") > 0
        assert VersionUtils.VersionComparer.version_str_compare("4.08", "4.08.01") < 0
        assert VersionUtils.VersionComparer.version_str_compare("3.2.1.9.8144", "3.2") > 0
        assert VersionUtils.VersionComparer.version_str_compare("3.2", "3.2.1.9.8144") < 0
        assert VersionUtils.VersionComparer.version_str_compare("1.2", "2.1") < 0
        assert VersionUtils.VersionComparer.version_str_compare("2.1", "1.2") > 0
        assert VersionUtils.VersionComparer.version_str_compare("5.6.7", "5.6.7") == 0
        assert VersionUtils.VersionComparer.version_str_compare("1.01.1", "1.1.1") == 0
        assert VersionUtils.VersionComparer.version_str_compare("1.1.1", "1.01.1") == 0
        assert VersionUtils.VersionComparer.version_str_compare("1", "1.0") == 0
        assert VersionUtils.VersionComparer.version_str_compare("1.0", "1") == 0
        assert VersionUtils.VersionComparer.version_str_compare("1.0", "1.0.1") < 0
        assert VersionUtils.VersionComparer.version_str_compare("1.0.1", "1.0") > 0
        assert VersionUtils.VersionComparer.version_str_compare("1.0.2.0", "1.0.2") == 0


if __name__ == '__main__':
    unittest.main()
