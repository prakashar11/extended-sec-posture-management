#! /usr/bin/env bash

# ls -al
# nohup /opt/asf/tools/alertmonitor/alertmon.sh &
# python3 -m venv ./
# . bin/activate
cd frontend/asfui
# copy static files - required first time
python3 manage.py collectstatic --noinput # https://docs.djangoproject.com/en/3.1/howto/static-files/
python3 manage.py makemigrations
python3 manage.py migrate
#python3 manage.py createsuperuser
export DJANGO_SUPERUSER_PASSWORD=admin
python3 manage.py createsuperuser \
      --noinput \
      --username=admin \
      --email='admin@localhost'
      # && ./setup-superuser.expect # to change admin password according to the one set in env variable

#exec nginx -g "daemon off;"
# cd /opt/asf/tools/systemd/
# for file in *
# do
# 	cp -v "$file" "/etc/systemd/system/$file" 
# done
# systemctl daemon-reload
# systemctl start asf
# systemctl enable asf
# systemctl enable cleanuptrash.timer
# systemctl start cleanuptrash.timer
# systemctl restart nginx
# service daemon-reload
# systemctl enable asf
# chkconfig asf on
# service asf start
# # systemctl enable cleanuptrash.timer
# chkconfig cleanuptrash.timer on
# service cleanuptrash.timer start
# Name of the application
NAME="asfui"
# Django project directory
DJANGO_DIR=/opt/asf/frontend/asfui
#we will communicte using this unix socket
SOCKFILE="$DJANGO_DIR/gunicorn.sock"
mkdir -p $DJANGO_DIR/logs
# the user to run as
#USER=asf
# the group to run as
# GROUP=asf
# how many worker processes should Gunicorn spawn
NUM_WORKERS=3
# which settings file should Django use
DJANGO_SETTINGS_MODULE=core.settings
# WSGI module name
DJANGO_WSGI_MODULE=core.wsgi
echo "Starting $NAME as `whoami`"
# Activate the virtual environment
# cd $DJANGO_DIR
# source $DJANGO_DIR/bin/activate
export DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE
export PYTHONPATH=$DJANGO_DIR:$PYTHONPATH
# Create the run directory if it doesn't exist
RUNDIR=$(dirname $SOCKFILE)
# (exec nginx -g "daemon off;") &&
test -d $RUNDIR || mkdir -p $RUNDIR
# Start your Django Unicorn
# Programs meant to be run under supervisor should not daemonize themselves (do not use --daemon)
#--user=$USER --group=$GROUP \
#--log-file=-
# (exec gunicorn ${DJANGO_WSGI_MODULE}:application \
# --name $NAME \
# --workers $NUM_WORKERS \
# # --bind=unix:$SOCKFILE \
# --bind 0.0.0.0:8080
# --log-level=debug \
# --log-file=$DJANGO_DIR/logs/gunicorn.log) &&
# ls -al /opt/asf/redteam/nuclei
# service docker start
# docker run -v /var/run/docker.sock:/var/run/docker.sock \
#            -ti docker
#cd /opt/asf/frontend/asfui/
python3 manage.py runserver 0.0.0.0:8080