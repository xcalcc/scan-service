import logging
import os
import unittest

# Please update this master file
OUTPUT_FILE=os.getenv("TEST_RESULT_FILE_PATH", "testing-result.txt")
MASTER_LINE = [
    "E..EE..............s.s...EEE.EEEEEE......sssssEss..........F....", # Server available but kafka not available
    "EEEEE..EEE.EEEEEEEE.....E", # No server available
]

def run_all_cases():
    suite = unittest.TestSuite()  # 创建测试套件
    # All File Names must follow this convention
    test_dir=os.path.dirname(__file__)
    all_cases = unittest.defaultTestLoader.discover(test_dir, 'test_*.py')
    # 找到某个目录下所有的以test开头的Python文件里面的测试用例
    for case in all_cases:
        suite.addTests(case)  # 把所有的测试用例添加进来


    # Start the runner process
    with open(OUTPUT_FILE, 'w') as fp:
        runner = unittest.TextTestRunner(stream=fp, verbosity=1, descriptions=True)
        runner.run(suite)

    with open(OUTPUT_FILE, "r") as fp:
        firstline = fp.readline(1000).strip("\n")
        for one_line in MASTER_LINE:
            logging.log(31, "MASTER  : %s", one_line)
        logging.log(31, "CURRENT : %s", firstline)

        if len(firstline) != len(MASTER_LINE[0]):
            logging.error("REMASTER: This test case runner is outdated, please update the testing result Master line.")
            exit(1)

        if firstline not in MASTER_LINE:
            logging.error("FAIL: Some tests have failed, see above or testing-result.txt for details:")
            exit(2)

        logging.log(31, "PASS: Testing revealed NO difference compared with Master line")

    pass

if __name__ == "__main__":
    run_all_cases()