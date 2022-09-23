import unittest

from tests.TestConfig import TestingUtility
from scanTaskService.components import LoggingHandler


class TestOfTestingUtility(unittest.TestCase):
    def test_01(self):
        res = TestingUtility.get_token()
        assert res is not None

if __name__ == "__main__":
    # Initialize logging utilities
    LoggingHandler.initialize_logging_utilities()
    unittest.main()