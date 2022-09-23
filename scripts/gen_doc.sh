for one in `find . -path ./doc -prune -o -name '*.py' -type f`
do
    echo "In file  = ${one}"
    res_file=../doc/${one}.txt
    echo "Out file = "${res_file}
    mkdir -p $(dirname ${res_file})
    python3 -m pydoc ${one} >${res_file}
done
