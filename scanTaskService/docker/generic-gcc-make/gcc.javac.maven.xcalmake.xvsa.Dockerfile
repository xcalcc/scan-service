ARG BASE="10.10.2.117:5000/sdlc.gcc.maven:1.0"
FROM $BASE

ARG XCAL_HOME=/home/xcalibyte
WORKDIR $XCAL_HOME

COPY start.sh /ws/xcal/app/scan/docker/generic-gcc-make

COPY dependency/xvsa.tar.gz $XCAL_HOME/dependency/xvsa.tar.gz
COPY dependency/xcal-wrapper-installer-latest.sh $XCAL_HOME/dependency/xcal-wrapper-installer-latest.sh

RUN mkdir $XCAL_HOME/xvsa && \
    tar zxf $XCAL_HOME/dependency/xvsa.tar.gz -C $XCAL_HOME/xvsa && \
    bash $XCAL_HOME/dependency/xcal-wrapper-installer-latest.sh $XCAL_HOME/preprocess && \
    rm -fr $XCAL_HOME/dependency

COPY dependency/xvsa_scan.sh $XCAL_HOME/xvsa/bin/xvsa_scan
RUN chmod +x $XCAL_HOME/xvsa/bin/xvsa_scan
ENV PATH=$PATH:$XCAL_HOME/xvsa/bin

CMD ["which", "xvsa", "xcalmake", "xvsa_scan"]