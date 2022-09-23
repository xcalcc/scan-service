FROM python:3.5-slim

ARG XCAL_HOME=/ws/xcal/app/scan
WORKDIR /home/xcalibyte

#install docker, python3 and jaeger
RUN apt-get update && \
    apt-get -y install python3-pip python3-setuptools git-core ssh --no-install-recommends && \
    apt-get autoclean && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install requests flask flask-restful docker prometheus_client kafka-python jaeger-client

#Copy python source code into the container at /ws/xcal/app/scan
#Run docker build -t <image>:<tag> -f scanTaskService/docker/ws.scan.Dockerfile . (Run this command at the root path of the xcalscan project
COPY scanTaskService/docker $XCAL_HOME/docker
COPY scanTaskService/src $XCAL_HOME

WORKDIR $XCAL_HOME