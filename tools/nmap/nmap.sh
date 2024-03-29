#!/bin/bash
INSTALLED_PATH=/opt/asf
OUTPUT_FOLDER="$INSTALLED_PATH/toolsrun/nmap/reports"
INPUT_FOLDER="$INSTALLED_PATH/toolsrun/nmap"
cd $INSTALLED_PATH/frontend/asfui
REGEX=$1
echo $REGEX
# . bin/activate
# this may need to be controlled through a flag - either to start scanning target input by user or
# to scan the domains discovered by amass/subfinder
# python3 manage.py nmap_input --input targets --filter "$REGEX" --output "$INPUT_FOLDER/targets.txt"
python3 manage.py nmap_input --input amass --filter "$REGEX" --output "$INPUT_FOLDER/targets_amass.txt"
python3 manage.py nmap_input --input subfinder --filter "$REGEX" --output "$INPUT_FOLDER/targets_subfinder.txt"
if ! test -e "$INPUT_FOLDER/targets.txt" || ! test -e "$INPUT_FOLDER/targets_amass.txt" || ! test -e "$INPUT_FOLDER/targets_subfinder.txt"
then 
	echo "No input targets detected"
	exit 1
fi
mkdir -p "$OUTPUT_FOLDER"
> "$INSTALLED_PATH/toolsrun/nmap/reports/nmap.lock"
cat "$INPUT_FOLDER/targets_subfinder.txt" >> "$INPUT_FOLDER/targets.txt"
cat "$INPUT_FOLDER/targets_amass.txt" >> "$INPUT_FOLDER/targets.txt"

#This line is for override and debug
#echo scanme.nmap.org > "$INPUT_FOLDER/targets.txt"
#echo 192.168.11.102 >> "$INPUT_FOLDER/targets.txt"
#echo 192.168.11.77 >> "$INPUT_FOLDER/targets.txt"
#echo 192.168.11.116 >> "$INPUT_FOLDER/targets.txt"
#echo 192.168.1.254 >> "$INPUT_FOLDER/targets.txt"
#echo 127.0.0.1 >> "$INPUT_FOLDER/targets.txt"

SNGHOSTS="127.0.0.1"
BLACKLST="10.206.96.68"
LOGDIR="$INSTALLED_PATH/toolsrun/netlog/var/log/madnmap/"
WORKERS="64"
TIMEOUT="360s"
ABORTTM="480s"
WPIDS=""
DELTAD=`date +%Y%m%d%H%M%S`

mkdir -p "$LOGDIR/$DELTAD"
mkdir -p "/tmp/$DELTAD.madnmap"
mkdir -p "$OUTPUT_FOLDER/$DELTAD"
#Worker Fullfillment
for WORKER in `seq 1 $WORKERS`
    do
    WFILE="/tmp/$DELTAD.madnmap/worker_$WORKER.sh"
    echo "#!/bin/bash">$WFILE
    chmod +x $WFILE
done
WORKER=1
JOBID=1
sort -u "$INPUT_FOLDER/targets.txt" -o "$INPUT_FOLDER/targets.txt.unique"
cat "$INPUT_FOLDER/targets.txt.unique" | while read H
    do 
    WFILE="/tmp/$DELTAD.madnmap/worker_$WORKER.sh"
    #echo "echo Scanning host $H Thread:$WORKER; timeout -k $ABORTTM $TIMEOUT nmap --top-ports 200 -p- -Pn -T4 --open --reason -oA $OUTPUT_FOLDER/$DELTAD/Worker_$WORKER.$JOBID.txt -sC $H >> $OUTPUT_FOLDER/$DELTAD/Worker_$WORKER.log" >> "$WFILE"
    echo "echo Scanning host $H Thread:$WORKER; timeout -k $ABORTTM $TIMEOUT nmap -sC -sV -Pn -T4 --open --reason -oA $OUTPUT_FOLDER/$DELTAD/Worker_$WORKER.$JOBID.txt -sC $H >> $OUTPUT_FOLDER/$DELTAD/Worker_$WORKER.log" >> "$WFILE"
    echo "cd '$INSTALLED_PATH/frontend/asfui'" >> "$WFILE"
    # echo ". bin/activate" >> "$WFILE"
	echo "python3 manage.py nmapparse --input $OUTPUT_FOLDER/$DELTAD/Worker_$WORKER.$JOBID.txt --host $H --destination external" >> "$WFILE"
    if test "$WORKER" -ge "$WORKERS"
	then WORKER=1
	else WORKER=$[$WORKER+1]
    fi
    JOBID=$[$JOBID+1]
done
#Cranking workers
for WORKER in `seq 1 $WORKERS`
    do
    WFILE="/tmp/$DELTAD.madnmap/worker_$WORKER.sh"
    $WFILE &
    #Collect PIDs of Nmap process
    WPID="$WPID $!"
done
#In case we cancel or terminate process, kill all subprocesses before exit
trap "kill -SIGTERM $WPID" SIGTERM
while sleep 60 
    do 
    WLEFT=`ps -Af | grep -v grep | grep "/tmp/$DELTAD.madnmap/worker" | wc -l`
	echo "Launched $WORKERS Threads, waiting to finish $WLEFT";
    if test "$WLEFT" "=" "0"
	then
		echo "No more Hosts, Finished"
		rm -fv "$INSTALLED_PATH/toolsrun/nmap/reports/nmap.lock"
		break
	else sleep 60
    fi
    sleep 60
done
echo "Finished"
#rm -fv "/home/nmap/reports/nmap.lock"
#exit 0
#UnComment for production
#trap
#rm -rf "/tmp/$DELTAD.madnmap/"
