
if [ -f ZK_DOCKER ] ; then
    docker rm $(cat ZK_DOCKER)
    docker rm $(cat KAFKA_DOCKER)
fi

docker run -d -p 2181:2181 --name zookeeper jplock/zookeeper > ZK_DOCKER
sleep 40s;
docker run -d --name kafka -p 9092:9092 -e KAFKA_ADVERTISED_HOST_NAME=39.108.212.149 --link zookeeper:zookeeper ches/kafka > KAFKA_DOCKER

# Local Run:
# docker run -d --name kafka -e KAFKA_ADVERTISED_HOST_NAME=127.0.0.1 -p 9092:9092 --link zookeeper:zookeeper xcal.kafka:0.1
