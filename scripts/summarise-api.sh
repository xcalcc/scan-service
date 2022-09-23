#!/usr/bin/env bash
### Diff tool for comparing the APIs present in all python code.

rm ./api.def.out
find . | grep .py$ | xargs grep -h "@app.route" -A1 >./api.def.out
diff ./api.def.out ./api.def.master
RET=$?
if [ $RET -ne 0 ]; then
  echo "Checking if diff exists between API and master file. [FAIL], exit with $RET"
  exit 2
fi

echo "Checking if diff exists between API and master file. [OK]"
exit 0