FROM python:3.11.0-slim-bullseye@sha256:1cd45c5dad845af18d71745c017325725dc979571c1bbe625b67e6051533716c as base
#FROM 3.11.1-alpine:3.17 as base
FROM base as build
# make sure to pass the host folder to the container as the same is used to mount volume in the container invoked inside
# container
ENV HOST_FOLDER $HOST_FOLDER
# copy source and install dependencies
RUN mkdir -p /opt/asf
RUN mkdir -p /opt/asf/frontend
RUN mkdir -p /opt/asf/images
RUN mkdir -p /opt/asf/redteam
RUN mkdir -p /opt/asf/tools
# RUN mkdir -p /opt/asf/pip_cache
# RUN mkdir -p /home/asf
RUN mkdir -p /opt/asf/jobs
RUN mkdir -p /opt/asf/toolsrun
RUN mkdir -p /opt/asf/toolsrun/nmap.int
RUN mkdir -p /opt/asf/toolsrun/nuclei-templates
# RUN mkdir -p /mnt
RUN mkdir -p /opt/asf/toolsrun
RUN mkdir -p /opt/asf/frontend/asfui/core/db
RUN mkdir -p /opt/asf/frontend/asfui/core/db/db
RUN mkdir -p /var/log/
WORKDIR /opt/asf
RUN \
  apt-get -y update && \
  apt-get -y install --no-install-recommends \
    imagemagick \
    #python3-venv \
    psmisc \
    psutils \
    nmap \
    hydra \
    curl \
    wget \
    tcpdump \
    vim \
    # docker.io \
    # docker-compose \
    python3-pip \
    ca-certificates \
    apt-transport-https \
    procps \
    git \
    # uuid-runtime \
    # systemd \
    # nginx \
    && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists && \
  true
COPY entrypoint.sh frontend/asfui/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache \
    pip install -r requirements.txt
COPY frontend ./frontend
COPY images ./images
COPY redteam ./redteam
COPY tools ./tools
# RUN git clone https://github.com/projectdiscovery/nuclei-templates.git /opt/asf/toolsrun/nuclei-templates
# VOLUME /var/run

# RUN pip install -r requirements.txt --cache-dir /opt/asf/pip_cache
# CPUCOUNT=1 is needed, otherwise the wheel for uwsgi won't always be build succesfully
# https://github.com/unbit/uwsgi/issues/1318#issuecomment-542238096
# COPY tools/nginx/sites-enabled/asf /etc/nginx/sites-enabled/
# RUN ln -sf /dev/stdout /var/log/nginx/access.log \
#     && ln -sf /dev/stderr /var/log/nginx/error.log \
#     && ln -s ./tools/scripts/startasf.sh /bin/
#RUN CPUCOUNT=1 pip3 wheel --wheel-dir=/tmp/wheels -r ./requirements.txt
EXPOSE 8080
STOPSIGNAL SIGTERM
USER root
ARG USER
ARG USER_ID
ARG GROUP
ARG DOCKERGID
ARG uid=${USER_ID}
ARG gid=${GROUP}
RUN addgroup --gid ${gid} ${USER} 
# RUN useradd -g ${gid} -G ${DOCKERGID} -M -N -u ${USER_ID} ${USER}
RUN adduser --uid ${uid} --gid ${gid} --no-create-home --disabled-password ${USER}
RUN chgrp -R $gid /opt/asf
RUN chown -R ${USER}:${USER} /opt/asf 
RUN chown -R ${USER}:${USER} /var/log
RUN chmod -R 775 /opt/asf
RUN usermod -a -G root ${USER} 
RUN groupadd docker
RUN groupmod -g ${DOCKERGID} docker
RUN usermod -aG docker ${USER}

USER ${USER}
# CMD ["./entrypoint.sh"]
ENTRYPOINT ["./entrypoint.sh"]
