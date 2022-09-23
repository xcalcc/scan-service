# Based on the agent/xvsa image
FROM daocloud.io/library/centos:7
ADD ./ci/Centos-7.repo /etc/yum.repos.d/CentOS-Base.repo
RUN yum -y install java-1.8.0-openjdk  \
    git  \
    maven  \
    which  \
    wget  \
    unzip  \
    bison  \
    flex  \
    make  \
    gcc  \
    gcc-c++  \
    glibc-devel \
    glibc-devel.i686  \
    glibc-static  \
    expect \
    python36 \
    sudo \
    libstdc++-devel \
    libstdc++-static 

RUN export CC=gcc && export CXX=g++
RUN JAVA_HOME=`readlink -f $(which java)|awk -F "/jre" '{print$1}'` && \
    ln -sf $JAVA_HOME /usr/lib/jvm/java-8-openjdk-amd64

ADD ./ci/requirements.txt /home/sanity/ci/requirements.txt
ADD ./requirements.txt /home/sanity/ci/requirements-2.txt

# Starting to add more.
RUN pip3 install \
       -r /home/sanity/ci/requirements-2.txt \
       -i https://pypi.douban.com/simple/

RUN pip3 install \
       -r /home/sanity/ci/requirements.txt \
       -i https://pypi.douban.com/simple/

ADD ./ci /home/sanity/ci
ADD ./scanTaskService/src /home/sanity

RUN yum clean all && rm -rf /var/cache/yum

CMD ["bash","-c","/home/sanity/ci/docker-entry.sh"]
