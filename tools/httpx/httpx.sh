#!/bin/bash
function debugsub {
    DATESTAMP=$(date '+%Y%m%d%H%M%S')
    echo -e "${DATESTAMP}\t $1 $2 $3 $4 $5" >> /var/log/subfinder.log
}
#. /opt/asf/tools/subfinder/subfinder.hack
DSTAMP=$(date '+%Y%m%d%H%M')
IMAGE="projectdiscovery/httpx"
docker pull $IMAGE:latest
INSTALLED_PATH="/opt/asf"
OUTPUT_DIR_PATH="$INSTALLED_PATH/toolsrun/discovery"
WDIR=`pwd`
mkdir -p "${OUTPUT_DIR_PATH}/reports"
mkdir -p "${OUTPUT_DIR_PATH}/history"
debugsub "Created folders and Time Stamp"
if test -e "${OUTPUT_DIR_PATH}/.lock"
	then echo "Already running"
		debugsub "Quitting because already running"
		exit 1
fi
debugsub "Creating lock file"
echo > "${OUTPUT_DIR_PATH}/.lock"
debugsub "Extracting from system app.input using parse_tools"
# cd /opt/asf/frontend/asfui/
# . bin/activate
# TODO: need to parse amass target as well
python3 manage.py nmap_input --input subfinder --output "${OUTPUT_DIR_PATH}/history/${DSTAMP}_targets.txt"
# python3 manage.py parse_tools --parser=subfinder.input --output="${OUTPUT_DIR_PATH}/history/${DSTAMP}_targets.txt"
# rm -v "${OUTPUT_DIR_PATH}/domaintargets.txt"
#ln -s "${OUTPUT_DIR_PATH}/history/${DSTAMP}_targets.txt" "${OUTPUT_DIR_PATH}/targets.txt"
cp "${OUTPUT_DIR_PATH}/history/${DSTAMP}_targets.txt" "${INSTALLED_PATH}/jobs/domaintargets.txt"
#docker pull $IMAGE
echo "Executing.."
#Lock
debugsub "Running httpx"
echo "docker run --rm -i $IMAGE -title -status-code -tech-detect -json -follow-redirects -<${INSTALLED_PATH}/jobs/domaintargets.txt 2>&1 | tee -a ${OUTPUT_DIR_PATH}/history/${DSTAMP}_discovery.log | grep -e "^{" | python3 manage.py parse_tools --parser=httpx.output --input=stdin 2>&1 | tee -a ${OUTPUT_DIR_PATH}/history/${DSTAMP}_run.log"
if docker run --rm -i $IMAGE -title -status-code -tech-detect -json -follow-redirects -<${INSTALLED_PATH}/jobs/domaintargets.txt 2>&1 | tee -a ${OUTPUT_DIR_PATH}/history/${DSTAMP}_discovery.log | grep -e "^{" | python3 manage.py parse_tools --parser=httpx.output --input=stdin 2>&1 | tee -a ${OUTPUT_DIR_PATH}/history/${DSTAMP}_run.log
then 
	echo "done"
	debugsub "Success running"
	rm -v "${OUTPUT_DIR_PATH}/.lock"
	rm -v "${INSTALLED_PATH}/jobs/domaintargets.txt"
else
	echo "Error running subfinder from docker, please check"
	debugsub "Subfinder error while running"
	rm -v "${OUTPUT_DIR_PATH}/.lock"
	rm -v "${INSTALLED_PATH}/jobs/domaintargets.txt"
	exit 1
fi
cd "$WDIR"
