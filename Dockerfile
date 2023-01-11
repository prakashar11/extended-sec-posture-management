FROM python:3.11.0-slim-bullseye@sha256:1cd45c5dad845af18d71745c017325725dc979571c1bbe625b67e6051533716c as base
#FROM 3.11.1-alpine:3.17 as base
FROM base as build
# copy source and install dependencies
RUN mkdir -p /opt/asf
RUN mkdir -p /opt/asf/frontend
RUN mkdir -p /opt/asf/images
RUN mkdir -p /opt/asf/redteam
RUN mkdir -p /opt/asf/tools
RUN mkdir -p /opt/asf/pip_cache
RUN mkdir -p /home/asf
RUN mkdir -p /opt/asf/jobs
RUN mkdir -p /home/nmap.int
RUN mkdir -p /mnt
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
# USER root
# ARG uid=1001
# ARG gid=1337
# ARG appuser=asfuser
# ENV appuser ${appuser}
# RUN \
#     addgroup --gid ${gid} ${appuser} && \
#     adduser --system --no-create-home --disabled-password --gecos '' \
#         --uid ${uid} --gid ${gid} ${appuser} && \
#     chown -R root:root /opt && \
#     chmod -R u+rwX,go+rX,go-w /opt && \
#     # Allow for bind mounting local_settings.py and other setting overrides
#     chown -R root:${appuser} /opt/asf && \
#     chmod -R 775 /opt/asf && \
#     mkdir /var/run/${appuser} && \
#     chown ${appuser} /var/run/${appuser} && \
# 	  chmod g=u /var/run/${appuser} && \
#     mkdir -p media/threat && chown -R ${uid} media
# USER ${uid}
# CMD ["./entrypoint.sh"]
ENTRYPOINT ["./entrypoint.sh"]