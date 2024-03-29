# -*- encoding: utf-8 -*-
from django.utils.safestring import mark_safe
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.template import loader
from django.http import HttpResponse
from django import template
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from datetime import date, datetime, timedelta
import time
import ast

from .models import vdTarget, vdInTarget, vdResult, vdServices, vdInServices, vdRegExp, vdJob, vdNucleiResult, vdNucleiTemplate

from os import path
import pathlib
import sys
import subprocess
import os
import re
import csv
import shutil
import json
import ruamel.yaml
import hashlib
from app.tools import *
from app.search import *
from app.systemd import sdService, DaysOfWeek
from app.metasploitbr import *
from app.targets import *
from app.nuclei import *
from app.discovery import *
import logging
from xml.etree import ElementTree as ET
from django.utils import timezone

GENERAL_PAGE_SIZE = 50

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TOOL_SCRIPT_DIR = os.path.join(BASE_DIR, "tools/")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler()
logger.addHandler(consoleHandler)

class CommandExecutionError(Exception):
    """Exception raised when en error occurred during linux command call"""
    pass

def pager(context, page, page_size, count):
    if page<0:
        page = 0
    if int((page + 1) * page_size) > count:
        page = int(count / page_size)
    start = page * page_size
    stop = start + page_size
    if stop > count:
        stop = count
        start = int(count / page_size) * page_size
    context['query_page'] = page
    context['query_page_next'] = page + 1
    if page > 0:
        context['query_page_prev'] = page - 1
    else:
        context['query_page_prev'] = 0
        context['query_page_next'] = 1
    
    return slice(start,stop)

@login_required(login_url="/login/")
def nuclei(request):
    context = {}
    context['segment'] = 'vd-nuclei'
    global PARSER_DEBUG
    PARSER_DEBUG=True
    debug(request.POST)
#Delete a NucleiFinding
    def nuclei_delete():
        nuclei_delete_model(request.POST)

    def nuclei_false():
        nuclei_tfp_model(request.POST)

    def nuclei_true():
        nuclei_tfp_model(request.POST)
        
    def nuclei_bump():
        nuclei_tfp_model(request.POST)

    def nuclei_ptime():
        set_nuclei_ptime(request.POST)
#Dirty solution since python lacks of switch case :\
    action={'true':nuclei_true, 'false':nuclei_false, 'delete':nuclei_delete, 'bump':nuclei_bump, 'ptime':nuclei_ptime}
    if 'nuclei_action' in request.POST:
        if request.POST['nuclei_action'] in action:
            action[request.POST['nuclei_action']]()

#Query all objects    
    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        # page = int(request.POST['page'])
        page_payload = request.POST['page']
        logger.debug(f"page_payload {page_payload}")
        page = int(page_payload.split(',')[0])
        severity_search = page_payload.split(',')[1]
        status_search = page_payload.split(',')[2]
        to_date = page_payload.split(',')[3]
        from_date = page_payload.split(',')[4]
        logger.debug(f"page handling value page:{page}, severity:{severity_search}, status:{status_search}, to_date: {to_date}, from_date: {from_date}")
        if severity_search and status_search:
            context['query_results'] = vdNucleiResult.objects.filter(level=severity_search, status=status_search)
        elif severity_search and not status_search:
            context['query_results'] = vdNucleiResult.objects.filter(level=severity_search)
        elif not severity_search and status_search:
            context['query_results'] = vdNucleiResult.objects.filter(status=status_search)
        else:
            context['query_results'] = vdNucleiResult.objects.all()
        if to_date and from_date:
            context['to_date'] = to_date
            context['from_date'] = from_date
            tz = timezone.get_current_timezone()
            enddate = datetime.strptime(to_date, '%m-%d-%Y').replace(tzinfo=tz)
            startdate = datetime.strptime(from_date, '%m-%d-%Y').replace(tzinfo=tz)
            # working around Django model time range search
            s_date = (startdate - timedelta(days=1)).replace(tzinfo=tz)
            e_date = (enddate + timedelta(days=1)).replace(tzinfo=tz)
            result = context['query_results']
            if enddate == startdate:
                # NOTE: firstdate is only updated at the time of creating finding
                # detection date and bump date are updated if finding already exists
                # TODO: why need for detection date and bump date?
                context['query_results'] = result.filter(firstdate__range=[s_date, e_date])
                # context['query_results'] = result.filter(firstdate__gt=startdate, firstdate__lt=enddate)
            else:
                context['query_results'] = result.filter(firstdate__range=[startdate, e_date])
        context['query_count'] = context['query_results'].count()
        context['severity_search'] = severity_search
        context['status_search'] = status_search
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
        context['nuclei_selector']=mark_safe(get_nuclei_ptime_selector(request.POST))
        context['nuclei_filter_hidden']=mark_safe(get_nuclei_filter_hidden(request.POST))
        html_template = loader.get_template( 'vd-nuclei.html' )
        return HttpResponse(html_template.render(context, request)) 


    # if 'domain_search' in request.POST:
    #     DomainRegexpFilter=request.POST['domain_search']
    #     context['domain_search'] = DomainRegexpFilter
    #     #context['query_results'] = vdResult.objects.filter(name__regex=DomainRegexpFilter)
    #     context['query_results'] = search(DomainRegexpFilter, 'nuclei')
    #     filters,context['query_results'] = nuclei_filter(request.POST,context['query_results'])
    #     context.update(filters)
                
    #     context['query_count'] = context['query_results'].count()
    #     #context['query_count'] = len(context['query_results'])
    #     slicer = pager(context, page, page_size, context['query_count'])
    #     context['query_results'] = context['query_results'][slicer]
    if 'severity_search' in request.POST or 'status_search' in request.POST or 'text_search' in request.POST or 'from_date' in request.POST or 'to_date' in request.POST:
        logger.debug(f"search POST {request.POST}")
        status_search = request.POST['status_search']
        severity_search = request.POST['severity_search']
        text_search = request.POST['text_search']
        # logger.debug(f"severity_search value {severity_search}")
        # logger.debug(f"status_search value {status_search}")
        to_date = request.POST['to_date']
        from_date = request.POST['from_date']
        if severity_search and status_search and text_search:
            # context['query_results'] = vdNucleiResult.objects.filter(level=severity_search, status=status_search)
            partial = vdNucleiResult.objects.filter(level=severity_search, status=status_search, name__regex=text_search)
            partial = partial | vdNucleiResult.objects.filter(level=severity_search, status=status_search, full_uri__icontains=text_search)
            result = partial | vdNucleiResult.objects.filter(level=severity_search, status=status_search, vulnerability__icontains=text_search)
            context['query_results'] = result
        elif severity_search and not status_search and not text_search:
            context['query_results'] = vdNucleiResult.objects.filter(level=severity_search)
        elif not severity_search and status_search and not text_search:
            context['query_results'] = vdNucleiResult.objects.filter(status=status_search)
        elif not severity_search and not status_search and text_search:
            partial = vdNucleiResult.objects.filter(name__regex=text_search)
            partial = partial | vdNucleiResult.objects.filter(full_uri__icontains=text_search)
            result = partial | vdNucleiResult.objects.filter(vulnerability__icontains=text_search)
            context['query_results'] = result
        elif severity_search and not status_search and text_search:
            partial = vdNucleiResult.objects.filter(level=severity_search, name__regex=text_search)
            partial = partial | vdNucleiResult.objects.filter(level=severity_search, full_uri__icontains=text_search)
            result = partial | vdNucleiResult.objects.filter(level=severity_search, vulnerability__icontains=text_search)
            context['query_results'] = result
        elif not severity_search and status_search and text_search:
            partial = vdNucleiResult.objects.filter(status=status_search, name__regex=text_search)
            partial = partial | vdNucleiResult.objects.filter(status=status_search, full_uri__icontains=text_search)
            result = partial | vdNucleiResult.objects.filter(status=status_search, vulnerability__icontains=text_search)
            context['query_results'] = result
        elif severity_search and status_search and not text_search:
            context['query_results'] = vdNucleiResult.objects.filter(level=severity_search, status=status_search)
        else:
            context['query_results'] = vdNucleiResult.objects.all()
        if to_date and from_date:
            context['to_date'] = to_date
            context['from_date'] = from_date
            tz = timezone.get_current_timezone()
            enddate = datetime.strptime(to_date, '%m-%d-%Y').replace(tzinfo=tz)
            startdate = datetime.strptime(from_date, '%m-%d-%Y').replace(tzinfo=tz)
            # working around Django model time range search
            s_date = (startdate - timedelta(days=1)).replace(tzinfo=tz)
            e_date = (enddate + timedelta(days=1)).replace(tzinfo=tz)
            result = context['query_results']
            if enddate == startdate:
                # NOTE: firstdate is only updated at the time of creating finding
                # detection date and bump date are updated if finding already exists
                # TODO: why need for detection date and bump date?
                context['query_results'] = result.filter(firstdate__range=[s_date, e_date])
                # context['query_results'] = result.filter(firstdate__gt=startdate, firstdate__lt=enddate)
            else:
                context['query_results'] = result.filter(firstdate__range=[startdate, e_date])
                # context['query_results'] = result.filter(firstdate__gte=startdate, firstdate__lte=enddate)
        context['query_count'] = context['query_results'].count()
        context['severity_search'] = severity_search
        context['status_search'] = status_search
        context['text_search'] = text_search
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    # elif 'status_search' in request.POST:
    #     logger.debug(f"status_search POST {request.POST}")
    #     status_search = request.POST['status_search']
    #     logger.debug(f"status_search value {status_search}")
    #     if status_search:
    #         context['query_results'] = vdNucleiResult.objects.filter(status=status_search)
    #     else:
    #         context['query_results'] = vdNucleiResult.objects.all()
    #     context['query_count'] = context['query_results'].count()
    else:
        context['query_results'] = vdNucleiResult.objects.all()
        filters,context['query_results'] = nuclei_filter(request.POST,context['query_results'])
        context.update(filters)        
        context['query_count'] = context['query_results'].count()
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    context['nuclei_selector']=mark_safe(get_nuclei_ptime_selector(request.POST))
    context['nuclei_filter_hidden']=mark_safe(get_nuclei_filter_hidden(request.POST))
    html_template = loader.get_template( 'vd-nuclei.html' )
    return HttpResponse(html_template.render(context, request))    

@login_required(login_url="/login/")
def nucleitemplates(request):
    context = {}
    context['segment'] = 'vd-nuclei-templates'
    global PARSER_DEBUG
    PARSER_DEBUG=True

#Set NucleiTemplates
    def nuclei_blacklist():
        logger.debug(request.POST)
        return
    
    def refresh_nuclei_template_model():
        folder='/opt/asf/toolsrun/nuclei-templates/'
        for p in NUCLEI_TEMPLATE_EXTENSIONS_PATTERNS:
            pathlist = Path(folder).glob(p)
            for path in pathlist:
                filename = str(path)
                nucleifn=filename.replace(folder, "")
                with open(filename) as f:                    
                    # data = yaml.safe_load(f)
                    yaml = ruamel.yaml.YAML(typ='safe')
                    data = yaml.load(f)
                    # json_data = json.dumps(data)
                    # data = f.readlines()
                try:
                    # assume it is a new entry
                    severity = '' if not 'severity' in data['info'] else data['info']['severity']
                    Nentry = vdNucleiTemplate(template_id=data['id'], info=data, name=data['info']['name'], severity=severity, template=nucleifn)
                    Nentry.save()
                except:
                    # existing template; refresh the severity, name and info
                    Nentry = vdNucleiTemplate.objects.filter(name=data['id'])
                    Nentry.info = data
                    severity = '' if not 'severity' in data['info'] else data['info']['severity']
                    Nentry.severity = severity
                    Nentry.save()
        return

    def nuclei_get_template_file():
        folder='/opt/asf/toolsrun/nuclei-templates/'
        file_content_read = None
        template_file = request.POST['template_file']
        for p in NUCLEI_TEMPLATE_EXTENSIONS_PATTERNS:
            pathlist = Path(folder).glob(p)
            for path in pathlist:
                filename = str(path)
                nucleifn=filename.replace(folder, "")
                # logger.debug(f"file names {template_file} {nucleifn}")
                if template_file == nucleifn:
                    logger.debug(f"file matched for {template_file}")
                    with open(filename) as f:                    
                        # return the yaml file
                        data = yaml.safe_load(f) # dict returned
                        # file_content_read = json.dumps(data, indent = 2)
                        file_content_read = data
        return file_content_read
    
    def search_templates(RegExp, ExcludeRegExp):
        logger.debug(f"Searching Nuclei templates\n")
        results = vdNucleiTemplate.objects.none()
        partial = vdNucleiTemplate.objects.filter(name__iregex=RegExp)
        if ExcludeRegExp != "":
            partial = partial.exclude(name__iregex=ExcludeRegExp)
        results = results | partial
        # results = merge_results(partial, results)
        # logger.debug(f"name returned {results}")
        partial = vdNucleiTemplate.objects.filter(template__iregex=RegExp)
        if ExcludeRegExp != "":
            partial = partial.exclude(template__iregex=ExcludeRegExp)
        results = results | partial
        # results = merge_results(partial, results)
        # logger.debug(f"template returned {results}")
        partial = vdNucleiTemplate.objects.filter(template_id__iregex=RegExp)
        if ExcludeRegExp != "":
            partial = partial.exclude(template_id__iregex=ExcludeRegExp)
        # results = merge_results(partial, results)
        results = results | partial
        # logger.debug(f"template_id returned {results}")
        # partial = vdNucleiTemplate.objects.filter(info__iregex=RegExp)
        # if ExcludeRegExp != "":
        #     partial = partial.exclude(info__iregex=RegExp)
        # results = merge_results(partial, results)
        # results = results | partial
        return results

    # def is_ajax(request):
    #     return request.headers.get('x-requested-with') == 'XMLHttpRequest'

    logger.debug(f"{request.POST}")
#Dirty solution since python lacks of switch case :\
    action={'blacklist':nuclei_blacklist, 'refresh': refresh_nuclei_template_model}
    file_content_read = None
    logger.debug(f"{request.POST}")
    if 'nuclei_action' in request.POST:
        if request.POST['nuclei_action'] in action:
            action[request.POST['nuclei_action']]()

    if 'template_file' in request.POST:
            # file_content_read = nuclei_get_template_file()
            file_content_read = vdNucleiTemplate.objects.filter(template=request.POST['template_file'])[0].info
    if file_content_read:
        file_dict = ast.literal_eval(file_content_read) # to make sure string converts to dict
        output = json.dumps(file_dict)
        context['file_content'] = {'file': request.POST['template_file'], 'content': output}

    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        page = int(request.POST['page'])
    
    ResultsExclude = ""
    if 'results_exclude' in request.POST:
        ResultsExclude=request.POST['results_exclude']
        context['results_exclude'] = ResultsExclude

    if 'results_search' in request.POST:
        ResultsSearch=request.POST['results_search']
        context['query_results'] = search_templates(ResultsSearch, ResultsExclude)
        # context['query_count'] = context['query_results'].count()
        context['query_count'] = len(context['query_results'])
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
        context['results_search'] = ResultsSearch
        context['show_save'] = True
    else:
        # nuclei_templates=get_nuclei_templates()
        # context['query_results']=get_nuclei_templates_4view(nuclei_templates)
        # set_nuclei_templates_4bl(request.POST, nuclei_templates)
        # context['query_count'] = context['query_results'].count()
        context['query_results'] = vdNucleiTemplate.objects.all()  
        context['query_count'] = len(context['query_results'])
        slicer = pager(context, page, page_size, context['query_count'])
        logger.debug(f"{slicer} {len(context['query_results'])}")
        context['query_results'] = context['query_results'][slicer]

    html_template = loader.get_template( 'vd-nuclei-templates.html' )
    return HttpResponse(html_template.render(context, request))  

@login_required(login_url="/login/")
def targets(request):
    context = {}
    context['segment'] = 'vd-targets'
#Add new domain or target
    def target_new():
        target_new_model(vdTarget,vdServices,request,context,autodetectType,delta)
#Delete a target
    def target_delete():
        target_delete_model(vdTarget,vdServices,request,context,autodetectType,delta)

    def get_external_ip():
        logger.debug("get external IP associated")
        timeout = None
        output = None
        cmd = f"curl -s http://whatismyip.akamai.com/"
        # get public external IP address associated
        # TODO also have to make osquery calls to other assets registered
        sub_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        try:
            output, errs = sub_proc.communicate(timeout=timeout)
            # byte to string
            extaddr = output.decode("utf-8")
        except Exception as e:
            sub_proc.kill()
            raise (e)
        else:
            if 0 != sub_proc.returncode:
                raise CommandExecutionError('Error during command: "' + ' '.join(cmd) + '"\n\n' + errs.decode('utf8'))
            if extaddr:
                # make an entry for the public IP
                Type = autodetectType(extaddr)
                tz = timezone.get_current_timezone()
                LastDate = datetime.now().replace(tzinfo=tz)
                Tag = "External IP"
                Result = vdTarget(name=extaddr, asset_type=Type, tag=Tag, lastdate=LastDate)
                try:
                    Result.save()
                    logger.debug(f"New external IP saved {extaddr}")
                except:
                    pass
            else:
                logger.warning("error getting external address")
            return
        
#Dirty solution since python lacks of switch case :\
    action={'new':target_new, 'delete':target_delete, 'extaddr': get_external_ip}
    if 'target_action' in request.POST:
        if request.POST['target_action'] in action:
            action[request.POST['target_action']]()
    
#Query all objects    
    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        page = int(request.POST['page'])
        
    if 'domain_search' in request.POST:
        DomainRegexpFilter=request.POST['domain_search']
        context['domain_search'] = DomainRegexpFilter
        #context['query_results'] = vdResult.objects.filter(name__regex=DomainRegexpFilter)
        context['query_results'] = search(DomainRegexpFilter, 'targets')
        context['query_count'] = context['query_results'].count()
        #context['query_count'] = len(context['query_results'])
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    else:
        context['query_results'] = vdTarget.objects.all()
        context['query_count'] = context['query_results'].count()
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]

    html_template = loader.get_template( 'vd-targets.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")
def dashboard(request):
    context = {}
    context['segment'] = 'vd-dashboard'
    # external asset details
    context['targets'] = vdTarget.objects.all().count()
    context['amass'] = str(vdResult.objects.all().count())
    context['subfinder_total'] = vdResult.objects.filter(engine='subfinder').count()
    context['subfinder_active'] = vdResult.objects.filter(engine='subfinder', active='Yes').count()
    # finding details
    context['num_critical'] = vdNucleiResult.objects.filter(level='critical').count()
    context['num_high'] = vdNucleiResult.objects.filter(level='high').count()
    context['num_medim'] = vdNucleiResult.objects.filter(level='medium').count()
    context['num_low'] = vdNucleiResult.objects.filter(level='low').count()
    context['num_info'] = vdNucleiResult.objects.filter(level='info').count()
    # SLA details
    tz = timezone.get_current_timezone()
    enddate = datetime.today().replace(tzinfo=tz)
    startdate = (enddate - timedelta(days=30)).replace(tzinfo=tz)
    context['sla_info'] = vdNucleiResult.objects.filter(firstdate__range=[startdate, enddate], level='info', status='open').count()
    context['sla_low'] = vdNucleiResult.objects.filter(firstdate__range=[startdate, enddate], level='low', status='open').count()
    # internal assets details
    context['internal_total'] = vdInTarget.objects.all().count()
    ObjWithServices = vdServices.objects.all()
    context['portscan'] = str(ObjWithServices.count())
    context['nuclei'] = []
    ports = {}
    for host in ObjWithServices:
        services = host.full_ports.split(", ")
        for service in services:
            data = service.split("/")
            port = data[0]
            if port not in ports:
                ports[port] = 1
            else:
                ports[port] += 1
        
        nuclei_http = host.nuclei_http.split("\n")
        if len(nuclei_http) > 0:
            for finding in nuclei_http:
                if len(finding) > 10 and len (context['nuclei']) < 200:
                    context['nuclei'].append(finding)
                
    sys.stderr.write(str(ports))
    context['totalports'] = len(ports)
    context['topports'] = []
    id=0
    for port in ports:
        context['topports'].append({'id':id, 'port':port, 'count': ports[port]})
        id += 1
        if id > 200:
            break
    html_template = loader.get_template( 'vd-dashboard.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")
def indashboard(request):
    context = {}
    context['segment'] = 'vd-in-dashboard'
    context['targets'] = str(vdTarget.objects.all().count())
    context['amass'] = str(vdResult.objects.all().count())
    sys.stderr.write("Amass Count:"+context['amass']+"\n")
    html_template = loader.get_template( 'vd-dashboard.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")
def intargets(request):
    context = {}
    context['segment'] = 'vd-in-targets'
#Add new domain or target
    def target_new():
        target_new_model(vdInTarget,vdInServices,request,context,autodetectType,delta)
        
#Delete a target
    def target_delete():
        target_delete_model(vdInTarget,vdInServices,request,context,autodetectType,delta)

    def parse_ports(xml_hosts):
        """
        Parse parts from xml
        """
        open_ports_list = []
        
        for port in xml_hosts.findall("ports/port"):
            open_ports = {}            
            for key in port.attrib:
                open_ports[key]=port.attrib.get(key)
                
            if(port.find('state') is not None):
                for key in port.find('state').attrib:
                    open_ports[key]=port.find("state").attrib.get(key)
           
            if(port.find('service') is not None):
                open_ports["service"]=port.find("service").attrib
                cpe_list = []
                for cp in port.find("service").findall("cpe"):
                    cpe_list.append({"cpe": cp.text})
                open_ports["cpe"] = cpe_list
            
            # Script
            # open_ports["scripts"]=self.parse_scripts(port.findall('script')) if port.findall('script') is not None else []
            open_ports_list.append(f"{open_ports}")
            
        return open_ports_list

    def target_discover():
        # referce: https://github.com/nmmapper/python3-nmap/blob/master/nmap3/nmapparser.py
        logger.debug("quick active target discovery")
        Targets = vdInTarget.objects.all()
        timeout = None
        output = None
        for target in Targets:
            # do this only for taget with wild card; no need to delete that target, but has to be skipped while
            # getting the target list
            logger.debug(f"processing target to make sure it is active {target.name}")
            # if autodetectType(target.name) == 'WILDCARD' or autodetectType(target.name) == 'CIDR':
            # nmap -PS -PU # would have been better as it also gets the ports/service information; but -PU requires sudo
            # nmap -sn (No port scan) -n (No DNS resolution. This speeds up our scan!) (was added after getting host with port 53)
            # -T4 (prohibits the dynamic scan delay from exceeding 10 ms for TCP ports)
            # 'nmap -F --open -oX - <target' # offers fast scan with XML results on open ports
            # cmd = f"nmap -sn -T4 -oX - {target.name}"
            cmd = f"nmap -F -T4 -oX - {target.name}"
            # discover hosts that are up if CIDR range or wild card is input as target
            sub_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            try:
                output, errs = sub_proc.communicate(timeout=timeout)
            except Exception as e:
                sub_proc.kill()
                raise (e)
            else:
                if 0 != sub_proc.returncode:
                    raise CommandExecutionError('Error during command: "' + ' '.join(cmd) + '"\n\n' + errs.decode('utf8'))
                if output:
                    # logger.debug(f"output from nmap scan {output}")
                    xmlroot = ET.fromstring(output.decode('utf8').strip())
                    scanned_host = xmlroot.findall("host")
                    for hosts in scanned_host:
                        address = hosts.find("address").get("addr")
                        Type = autodetectType(address)
                        # logger.debug(f"host address {address} type {Type}")
                        metadata = {}
                        metadata['owner']="Admin from UI"
                        Jmetadata = json.dumps(metadata)
                        # update Tag with hostnames
                        Tag = "Default"
                        hostnames = hosts.findall("hostnames/hostname")
                        hostnames_list = []
                        for host in hostnames:
                            if 'name' in host.attrib:
                                hostnames_list.append(host.attrib['name'])
                        if hostnames_list:
                            Tag = ';'.join(hostnames_list)
                        tz = timezone.get_current_timezone()
                        LastDate = datetime.now().replace(tzinfo=tz)
                        port_details = parse_ports(hosts)
                        # update target
                        try:
                            vdInTarget.objects.update_or_create(name=address, defaults={'asset_type': Type, 'tag':Tag, 'lastdate': LastDate, 'owner': metadata['owner'], 'metadata': Jmetadata}, info=json.dumps(port_details, indent=4))
                            logger.debug(f"completed vdInTarget update for {address} {Tag}")
                        except:
                            # directly updating the model
                            Results = vdInTarget.objects.filter(name=address)
                            for result in Results:
                                result.info = json.dumps(port_details, indent=4)
                                result.lastdate = LastDate
                                result.save()
                            logger.debug("vdInTarget model direct update")
                else:
                    logger.debug("error in getting output")
        
#Same dirty solution 
    action={'new':target_new, 'delete':target_delete, 'discover': target_discover}
    if 'target_action' in request.POST:
        if request.POST['target_action'] in action:
            action[request.POST['target_action']]()
            post = request.POST.copy() # to make it mutable
            post['target_action'] = ""
            request.POST = post
            logger.debug(f"updated request.POST to {request.POST}")
            
#Query all objects    
    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        page = int(request.POST['page'])
        
    if 'domain_search' in request.POST:
        DomainRegexpFilter=request.POST['domain_search']
        context['domain_search'] = DomainRegexpFilter
        #context['query_results'] = vdResult.objects.filter(name__regex=DomainRegexpFilter)
        context['query_results'] = search(DomainRegexpFilter, 'intargets')
        context['query_count'] = context['query_results'].count()
        #context['query_count'] = len(context['query_results'])
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    else:
        context['query_results'] = vdInTarget.objects.all()
        context['query_count'] = context['query_results'].count()
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    html_template = loader.get_template( 'vd-in-targets.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")     
def amass(request):
    context = {}
    context['segment'] = 'vd-amass'
    ensure_dirs("/opt/asf/toolsrun/amass/reports")

    if path.isfile("/opt/asf/toolsrun/discovery/.lock"):
        context['running'] = True
    else:
        context['running'] = False
#start amass
    def amass_start():
        subprocess.Popen(["/bin/bash", "/opt/asf/tools/amass/amass.sh"])
        # subprocess.Popen(["nohup", "/opt/asf/tools/subfinder/subfinder.sh"])
        context['running'] = True

#stop amass
    def amass_stop():
        sys.stdout.write("Stopping Amass")
        subprocess.Popen(["killall", "amass.sh"])
        # subprocess.Popen(["killall", "subfinder.sh"])
        #if path.exists("/home/amass/reports/amass.txt"):
        if path.exists("/opt/asf/toolsrun/discovery/.lock"):
            os.remove("/home/amass/reports/amass.txt")
            # os.remove("/opt/asf/toolsrun/discovery/.lock")
        subprocess.Popen(["killall", "amass"])
        # subprocess.Popen(["killall", "subfinder"])
        context['running'] = False
        return
    
    def amass_new():
        discovery_new(request,context,autodetectType,delta)
                
    def amass_delete():
        return discovery_delete(request,context,autodetectType,delta)
   
    def amass_total_purge():
        debug("Total Purge: Amass Host\n")
        try:
            HostName = vdResult.objects.all()
            HostName.delete()
        except Exception as e:
            sys.stdout.write(str(e))
        return

                
    def amass_partial_load():
        sys.stderr.write("Calling partial load from view, excecuting amassparse\n")
        try:
            call_command('amassparse')
        except Exception as e:
            sys.stderr.write(str(e)+"\n")
        return

    def amass_schedule():
        AmassService = sdService({"name":"vdamass"})
        AmassService.readTimerFromRequest(request)
        AmassService.config['Unit']['Description'] = "Attack Surface Framework Amass Service Files"
        AmassService.config['Unit']['Requires'] = "docker.service"
        AmassService.config['Service']['ExecStart'] = "/opt/asf/tools/amass/amass.sh" 
        # AmassService.config['Service']['ExecStart'] = "/opt/asf/tools/subfinder/subfinder.sh"
        AmassService.write()
        return True
    
#Same dirty solution
    action={'new': amass_new, 'start':amass_start, 'stop':amass_stop, 'delete':amass_delete, 'total_purge':amass_total_purge, 'partial_load':amass_partial_load, 'schedule':amass_schedule}
    if 'amass_action' in request.POST:
        if request.POST['amass_action'] in action:
            debug("Excecuting :"+request.POST['amass_action'])
            action[request.POST['amass_action']]()
    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        page = int(request.POST['page'])
        
    if 'domain_search' in request.POST:
        DomainRegexpFilter=request.POST['domain_search']
        context['domain_search'] = DomainRegexpFilter
        #context['query_results'] = vdResult.objects.filter(name__regex=DomainRegexpFilter)
        context['query_results'] = search(DomainRegexpFilter, 'amass')
        context['query_count'] = context['query_results'].count()
        #context['query_count'] = len(context['query_results'])
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    else:
        # context['query_results'] = vdResult.objects.all()
        context['query_results'] = vdResult.objects.filter(engine='amass')
        context['query_count'] = context['query_results'].count()
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    
    #Here we add data from the previous system timer, and pass it to the view via context dictionary
    AmassService = sdService({"name":"vdamass"})
    AmassService.read()
    AmassService.setContext(context)

    
    html_template = loader.get_template( 'vd-amass.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")     
def subfinder(request):
    context = {}
    context['segment'] = 'vd-subfinder'
    ensure_dirs("/opt/asf/toolsrun/subfinder/reports")

    if path.isfile("/opt/asf/toolsrun/discovery/.lock"):
        context['running'] = True
    else:
        context['running'] = False
#start subfinder
    def subfinder_start():
        subprocess.Popen(["/bin/bash", "/opt/asf/tools/subfinder/subfinder.sh"])
        context['running'] = True

#stop subfinder
    def subfinder_stop():
        timeout = None
        logger.debug("Stopping Subfinder")
        subprocess.Popen(["killall", "subfinder.sh"])
        # if path.exists("/opt/asf/toolsrun/discovery/.lock"):
        #     os.remove("/opt/asf/toolsrun/discovery/.lock")
        # subprocess.Popen(["killall", "subfinder"])
        cmd = 'docker container ls | grep "projectdiscovery/subfinder"'
        sub_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        try:
            output, errs = sub_proc.communicate(timeout=timeout)
        except Exception as e:
            sub_proc.kill()
            raise (e)
        else:
            if 0 != sub_proc.returncode:
                raise CommandExecutionError('Error during command: "' + ' '.join(cmd) + '"\n\n' + errs.decode('utf8'))
        container_id = output.decode('utf-8').split(' ')[0]
        cmd = f"docker kill {container_id}"
        sub_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        try:
            output, errs = sub_proc.communicate(timeout=timeout)
        except Exception as e:
            sub_proc.kill()
            raise (e)
        else:
            if 0 != sub_proc.returncode:
                raise CommandExecutionError('Error during command: "' + ' '.join(cmd) + '"\n\n' + errs.decode('utf8'))
        context['running'] = False
        return
    
    def subfinder_new():
        discovery_new(request,context,autodetectType,delta)
                
    def subfinder_delete():
        return discovery_delete(request,context,autodetectType,delta)
   
    def subfinder_total_purge():
        debug("Total Purge: Subfinder Host\n")
        try:
            HostName = vdResult.objects.all()
            HostName.delete()
        except Exception as e:
            sys.stdout.write(str(e))
        return

                
    def subfinder_partial_load():
        sys.stderr.write("Calling partial load from view, excecuting amassparse\n")
        try:
            call_command('amassparse')
        except Exception as e:
            sys.stderr.write(str(e)+"\n")
        return

    def subfinder_schedule():
        AmassService = sdService({"name":"vdamass"})
        AmassService.readTimerFromRequest(request)
        AmassService.config['Unit']['Description'] = "Attack Surface Framework Amass Service Files"
        AmassService.config['Unit']['Requires'] = "docker.service"
        AmassService.config['Service']['ExecStart'] = "/opt/asf/tools/subfinder/subfinder.sh"
        AmassService.write()
        return True
    
    def active_domains_discover():
        logger.debug(f"to call httpx to find active domains and update vdResult.active")
        subprocess.Popen(["/bin/bash", "/opt/asf/tools/httpx/httpx.sh"])

#Same dirty solution
    action={'new': subfinder_new, 'start':subfinder_start, 'stop':subfinder_stop, 'delete':subfinder_delete, 'total_purge':subfinder_total_purge, 'partial_load':subfinder_partial_load, 'schedule':subfinder_schedule, 'activedomains': active_domains_discover}

    if 'subfinder_action' in request.POST:
        if request.POST['subfinder_action'] in action:
            debug("Excecuting :"+request.POST['subfinder_action'])
            action[request.POST['subfinder_action']]()
    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        page = int(request.POST['page'])
        
    if 'domain_search' in request.POST:
        DomainRegexpFilter=request.POST['domain_search']
        context['domain_search'] = DomainRegexpFilter
        # context['query_results'] = vdResult.objects.filter(name__regex=DomainRegexpFilter)
        context['query_results'] = search(DomainRegexpFilter, 'subfinder')
        context['query_count'] = context['query_results'].count()
        #context['query_count'] = len(context['query_results'])
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    else:
        # context['query_results'] = vdResult.objects.all()
        context['query_results'] = vdResult.objects.filter(engine='subfinder')
        context['query_count'] = context['query_results'].count()
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
    
    #Here we add data from the previous system timer, and pass it to the view via context dictionary
    AmassService = sdService({"name":"vdamass"})
    AmassService.read()
    AmassService.setContext(context)

    
    html_template = loader.get_template( 'vd-subfinder.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")    
def portscan(request):
    context = {}
    context['segment'] = 'vd-portscan'
    # context['query_results'] = "Ninguno"
    # ensure_dirs("/opt/asf/toolsrun/nmap/reports")
    # page = 0
    # page_size = GENERAL_PAGE_SIZE
    # if 'page' in request.POST:
    #     page = int(request.POST['page'])
    
    # ResultsExclude = ""
    # if 'results_exclude' in request.POST:
    #     ResultsExclude=request.POST['results_exclude']
    #     context['results_exclude'] = ResultsExclude

    # if 'results_search' in request.POST:
    #     ResultsSearch=request.POST['results_search']
    #     #context['query_results'] = vdServices.objects.filter(info__regex=ResultsSearch)
    #     context['query_results'] = search(ResultsSearch, 'services', ResultsExclude)
    #     context['query_count'] = context['query_results'].count() 
    #     #context['query_count'] = len(context['query_results'])
    #     slicer = pager(context, page, page_size, context['query_count'])
    #     context['query_results'] = context['query_results'][slicer]
    #     context['results_search'] = ResultsSearch
    #     context['show_save'] = True
    # else:
    #     context['query_results'] = vdServices.objects.all()
    #     context['query_count'] = context['query_results'].count()
    #     slicer = pager(context, page, page_size, context['query_count'])
    #     context['query_results'] = context['query_results'][slicer]
    #     context['show_save'] = False
    # context['saved_regexp'] = vdRegExp.objects.all()[0:3000]
        
    # if path.isfile("/opt/asf/toolsrun/nmap/reports/nmap.lock"):
    #     context['running'] = True
    # else:
    #     context['running'] = False
        
    def host_picture(HostWithServices):
        NEW_HWS = []
        HOST_PICTURE_FOLDER="/opt/asf/frontend/asfui/core/static/hosts/"
        for Host in HostWithServices:
            PICTURE = "/static/assets/asf/logo4.png"
            if path.exists(HOST_PICTURE_FOLDER+Host.name):
                for file in os.listdir(HOST_PICTURE_FOLDER+Host.name):
                    if file.endswith(".png"):
                        PICTURE = "/static/hosts/"+Host.name+"/"+str(file)
                        break
            NEW_INFO = Host.info + "\n========== BruteForce ==========\n" + Host.service_ssh + Host.service_ftp +" "+ Host.service_rdp +" "+ Host.service_telnet + " " +  Host.service_smb + "\n\n========== Nuclei ==========\n" + Host.nuclei_http
            H = {'id':Host.id, 'screenshot':PICTURE, 'name':Host.name, 'nname':Host.nname, 'ipv4':Host.ipv4, 'lastdate':Host.lastdate, 'ports':Host.ports, 'info':NEW_INFO, 'owner':Host.owner, 'tag':Host.tag, 'metadata':Host.metadata}
            NEW_HWS.append(H)
        return NEW_HWS
        
#start Nmap
    def nmap_start():
        # subprocess.Popen(["nohup", "/opt/asf/tools/nmap/nmap.sh"])
        logger.debug(f"request {request.POST}")
        nmap_regexp = ''
        if 'nmap_regexp' in request.POST:
            jre = request.POST['nmap_regexp']
            qre = vdRegExp.objects.filter(id = jre).first()
            nmap_regexp = qre.regexp
            logger.debug(f"nmap_regexp {nmap_regexp}")
            # nmap_regexp = request.POST['nmap_regexp']
        nmap_path = os.path.join(TOOL_SCRIPT_DIR, 'nmap/nmap.sh')
        logger.debug(f"nmap path {nmap_path}")
        subprocess.Popen(["/bin/bash", nmap_path, str(nmap_regexp)])
        context['running'] = True

#stop Nmap
    def nmap_stop():
        sys.stdout.write("Stopping Nmap")
        subprocess.Popen(["killall", "nmap.sh"])
        if path.exists("/opt/asf/toolsrun/nmap/reports/nmap.lock"):
            os.remove("/opt/asf/toolsrun/nmap/reports/nmap.lock")
        #subprocess.Popen(["killall", "nmap"])
        os.system("killall nmap")
        context['running'] = False
        
    def nmap_save_regexp():
        regexp_name = "Default"
        if "regexp_name" in request.POST:
            regexp_name = request.POST['regexp_name']
        regexp_query = "Default"
        if 'regexp_query' in request.POST:
            regexp_query = request.POST['regexp_query']
        regexp_exclude = ""
        if 'regexp_exclude' in request.POST:
            regexp_exclude = request.POST['regexp_exclude']
        regexp_info = "Default"
        if 'regexp_info' in request.POST:
            regexp_info = request.POST['regexp_info']
        try:
            NewRegExp = vdRegExp(name = regexp_name, regexp = regexp_query, exclude = regexp_exclude, info = regexp_info)
            NewRegExp.save()
        except:
            sys.stderr.write("Duplicated RegExpr, Skipping:"+regexp_name)
            context['error'] = "Duplicated or Wrong Data"
    def nmap_delete_regexp():
        if "regexp_id" in request.POST:
            regexp_id = request.POST['regexp_id']
            try:
                RegExp = vdRegExp.objects.filter(id = regexp_id)
                RegExp.delete()
            except:
                sys.stderr.write("Inexistent ID, Skipping:"+regexp_name)
                context['error'] = "Inexistent or Wrong Data"
    def nmap_delete():
        if "id" in request.POST:
            id = request.POST['id']
            try:
                DeleteObj = vdServices.objects.filter(id = id)
                DeleteObj.delete()
            except:
                sys.stderr.write("Inexistent ID, Skipping:"+regexp_name)
                context['error'] = "Inexistent or Wrong Data"
                
    def nmap_schedule():
        ExNmap = sdService({"name":"vdexnmap"})
        ExNmap.readTimerFromRequest(request)
        ExNmap.config['Unit']['Description'] = "Attack Surface Framework External Nmap Service File"
        ExNmap.config['Unit']['Requires'] = "docker.service"
        ExNmap.config['Service']['ExecStart'] = "/opt/asf/tools/nmap/nmap.sh" 
        ExNmap.write()
        return
    
#Same dirty solution
    action={'start':nmap_start, 'stop':nmap_stop, 'save_regexp':nmap_save_regexp, 'delete_regexp':nmap_delete_regexp, 'delete':nmap_delete, 'schedule':nmap_schedule}
    if 'nmap_action' in request.POST:
        if request.POST['nmap_action'] in action:
            action[request.POST['nmap_action']]()   
    # context['query_results'] = "Ninguno"
    
    if not 'query_results' in context:
        context['query_results'] = ""

    ensure_dirs("/opt/asf/toolsrun/nmap/reports")
    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        page = int(request.POST['page'])
    
    #Here we add data from the previous system timer, and pass it to the view via context dictionary
    ExNmap = sdService({"name":"vdexnmap"})
    ExNmap.read()
    ExNmap.setContext(context)
    
    ResultsExclude = ""
    if 'results_exclude' in request.POST:
        ResultsExclude=request.POST['results_exclude']
        context['results_exclude'] = ResultsExclude

    if 'results_search' in request.POST:
        ResultsSearch=request.POST['results_search']
        #context['query_results'] = vdServices.objects.filter(info__regex=ResultsSearch)
        context['query_results'] = search(ResultsSearch, 'services', ResultsExclude)
        context['query_count'] = context['query_results'].count() 
        #context['query_count'] = len(context['query_results'])
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
        context['results_search'] = ResultsSearch
        context['show_save'] = True
    else:
        context['query_results'] = vdServices.objects.all()
        context['query_count'] = context['query_results'].count()
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
        context['show_save'] = False
    context['saved_regexp'] = vdRegExp.objects.all()[0:3000]
        
    if path.isfile("/opt/asf/toolsrun/nmap/reports/nmap.lock"):
        context['running'] = True
    else:
        context['running'] = False

    context['query_results'] = host_picture(context['query_results'])
    
    html_template = loader.get_template( 'vd-portscan.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")    
def inportscan(request):
    context = {}
    context['segment'] = 'vd-in-portscan'
    # context['query_results'] = "Ninguno"
    # ensure_dirs("/opt/asf/toolsrun/nmap.int/reports")
    # page = 0
    # page_size = GENERAL_PAGE_SIZE
    # if 'page' in request.POST:
    #     page = int(request.POST['page'])
    
    # ResultsExclude = ""
    # if 'results_exclude' in request.POST:
    #     ResultsExclude=request.POST['results_exclude']
    #     context['results_exclude'] = ResultsExclude

    # if 'results_search' in request.POST:
    #     ResultsSearch=request.POST['results_search']
    #     context['query_results'] = search(ResultsSearch, 'inservices', ResultsExclude)
    #     context['query_count'] = context['query_results'].count() 
    #     slicer = pager(context, page, page_size, context['query_count'])
    #     context['query_results'] = context['query_results'][slicer]
    #     context['results_search'] = ResultsSearch
    #     context['show_save'] = True
    # else:
    #     context['query_results'] = vdInServices.objects.all()
    #     context['query_count'] = context['query_results'].count()
    #     slicer = pager(context, page, page_size, context['query_count'])
    #     context['query_results'] = context['query_results'][slicer]
    #     context['show_save'] = False
    # context['saved_regexp'] = vdRegExp.objects.all()[0:3000]
        
    # if path.isfile("/opt/asf/toolsrun/nmap.int/reports/nmap.lock"):
    #     context['running'] = True
    # else:
    #     context['running'] = False
        
    def host_picture(HostWithServices):
        NEW_HWS = []
        HOST_PICTURE_FOLDER="/opt/asf/frontend/asfui/core/static/hosts/"
        for Host in HostWithServices:
            PICTURE = "/static/assets/asf/logo4.png"
            if path.exists(HOST_PICTURE_FOLDER+Host.name):
                for file in os.listdir(HOST_PICTURE_FOLDER+Host.name):
                    if file.endswith(".png"):
                        PICTURE = "/static/hosts/"+Host.name+"/"+str(file)
                        break
            NEW_INFO = Host.info + "\n========== BruteForce ==========\n" + Host.service_ssh + Host.service_ftp +" "+ Host.service_rdp +" "+ Host.service_telnet + " " +  Host.service_smb + "\n\n========== Nuclei ==========\n" + Host.nuclei_http
            H = {'id':Host.id, 'screenshot':PICTURE, 'name':Host.name, 'nname':Host.nname, 'ipv4':Host.ipv4, 'lastdate':Host.lastdate, 'ports':Host.ports, 'info':NEW_INFO, 'owner':Host.owner, 'tag':Host.tag, 'metadata':Host.metadata}
            NEW_HWS.append(H)
        return NEW_HWS
        
#start Nmap
    def nmap_start():
#         Targets=vdInTarget.objects.all()
#         FileTargets=open("/home/nmap.int/targets.txt",'w+')
#         for target in Targets:
#             FileTargets.write(target.name+"\n")
#         sys.stdout.write("Staring Nmap for Internal Networks")
#         FileTargets.close()
        #subprocess.Popen(["nohup", "/opt/asf/tools/nmap/nmap.int.sh"])
        logger.debug(f"{request.POST}")
        nmap_regexp = ''
        if 'nmap_regexp' in request.POST:
            jre = request.POST['nmap_regexp']
            qre = vdRegExp.objects.filter(id = jre).first()
            nmap_regexp = qre.regexp
            logger.debug(f"nmap_regexp {nmap_regexp}")
        nmap_path = os.path.join(TOOL_SCRIPT_DIR, 'nmap/nmap.int.sh')
        logger.debug(f"nmap path {nmap_path}")
        subprocess.Popen(["/bin/bash", nmap_path, str(nmap_regexp)])
        # subprocess.Popen(["/bin/bash", nmap_path, str(nmap_regexp)])
        #os.system("nohup /opt/asf/tools/nmap/nmap.sh")
        context['running'] = True

    def nmap_quick_scan():
        # referce: https://github.com/nmmapper/python3-nmap/blob/master/nmap3/nmapparser.py
        logger.debug("nmap quick scan")
        Targets = vdInTarget.objects.all()
        timeout = None
        output = None
        for target in Targets:
            # do this only for taget with wild card; no need to delete that target, but has to be skipped while
            # getting the target list
            logger.debug(f"processing target to make sure it is active {target.name}")
            # if autodetectType(target.name) == 'WILDCARD' or autodetectType(target.name) == 'CIDR':
            cmd = f"nmap -sn -n -T4 -oX - {target.name}"
            # discover hosts that are up if CIDR range or wild card is input as target
            sub_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            try:
                output, errs = sub_proc.communicate(timeout=timeout)
            except Exception as e:
                sub_proc.kill()
                raise (e)
            else:
                if 0 != sub_proc.returncode:
                    raise CommandExecutionError('Error during command: "' + ' '.join(cmd) + '"\n\n' + errs.decode('utf8'))
                if output:
                    logger.debug(f"output from nmap scan {output}")
                    xmlroot = ET.fromstring(output.decode('utf8').strip())
                    scanned_host = xmlroot.findall("host")
                    for hosts in scanned_host:
                        address = hosts.find("address").get("addr")
                        Type = autodetectType(address)
                        logger.debug(f"host address {address} type {Type}")
                        metadata = {}
                        metadata['owner']="Admin from UI"
                        Jmetadata = json.dumps(metadata)
                        # update Tag with hostnames
                        Tag = "Default"
                        hostnames = hosts.findall("hostnames/hostname")
                        hostnames_list = []
                        for host in hostnames:
                            if 'name' in host.attrib:
                                hostnames_list.append(host.attrib['name'])
                        if hostnames_list:
                            Tag = ';'.join(hostnames_list)
                        tz = timezone.get_current_timezone()
                        LastDate = datetime.now().replace(tzinfo=tz)
                        # update target
                        try:
                            # vdInTarget.objects.update_or_create(name=address, defaults={'type': Type, 'tag':Tag, 'lastdate': LastDate, 'owner': metadata['owner'], 'metadata': Jmetadata})
                            vdInServices.objects.update_or_create(name=address, nname=address, ipv4=address, tag=Tag, asset_type=Type, metadata = Jmetadata, owner = metadata['owner'])
                            logger.debug(f"completed vdInTarget update for {address} {Tag}")
                        except:
                            logger.debug("vdTarget model update failed")
                else:
                    logger.debug("error in getting output")
        context['running'] = False

# refresh nmap scan status
    def nmap_refresh():
        if path.isfile("/opt/asf/toolsrun/nmap.int/reports/nmap.lock"):
            context['running'] = True
        else:
            context['running'] = False
#stop Nmap
    def nmap_stop():
        sys.stdout.write("Stopping Nmap for Internal Networks")
        subprocess.Popen(["killall", "nmap.int.sh"])
        if path.exists("/opt/asf/toolsrun/nmap.int/reports/nmap.lock"):
            os.remove("/opt/asf/toolsrun/nmap.int/reports/nmap.lock")
        #We should not kill nmap, because external nmap could be running.
        #subprocess.Popen(["killall", "nmap"])
        os.system("killall nmap.int")
        context['running'] = False
        
    def nmap_save_regexp():
        regexp_name = "Default"
        if "regexp_name" in request.POST:
            regexp_name = request.POST['regexp_name']
        regexp_query = "Default"
        if 'regexp_query' in request.POST:
            regexp_query = request.POST['regexp_query']
        regexp_exclude = ""
        if 'regexp_exclude' in request.POST:
            regexp_exclude = request.POST['regexp_exclude']
        regexp_info = "Default"
        if 'regexp_info' in request.POST:
            regexp_info = request.POST['regexp_info']
        try:
            NewRegExp = vdRegExp(name = regexp_name, regexp = regexp_query, exclude = regexp_exclude, info = regexp_info)
            NewRegExp.save()
        except:
            sys.stderr.write("Duplicated RegExpr, Skipping:"+regexp_name)
            context['error'] = "Duplicated or Wrong Data"
            
    def nmap_delete_regexp():
        if "regexp_id" in request.POST:
            regexp_id = request.POST['regexp_id']
            try:
                RegExp = vdRegExp.objects.filter(id = regexp_id)
                RegExp.delete()
            except:
                sys.stderr.write("Inexistent ID, Skipping:"+regexp_name)
                context['error'] = "Inexistent or Wrong Data"
                
    def nmap_delete():
        if "id" in request.POST:
            id = request.POST['id']
            try:
                DeleteObj = vdInServices.objects.filter(id = id)
                DeleteObj.delete()
            except:
                sys.stderr.write("Inexistent ID, Skipping:"+regexp_name)
                context['error'] = "Inexistent or Wrong Data"

    def nmap_schedule():
        InNmap = sdService({"name":"vdinnmap"})
        InNmap.readTimerFromRequest(request)
        InNmap.config['Unit']['Description'] = "Attack Surface Framework Internal Nmap Service File"
        InNmap.config['Unit']['Requires'] = "docker.service"
        InNmap.config['Service']['ExecStart'] = "/opt/asf/tools/nmap/nmap.int.sh" 
        InNmap.write()
        return
    
#Same dirty solution
    action={'start':nmap_start, 'stop':nmap_stop, 'save_regexp':nmap_save_regexp, 'delete_regexp':nmap_delete_regexp, 'delete':nmap_delete, 'schedule': nmap_schedule, 'refresh': nmap_refresh, 'quick': nmap_quick_scan}
    logger.debug(f"request received {request.POST}")
    if 'nmap_action' in request.POST:
        if request.POST['nmap_action'] in action:
            action[request.POST['nmap_action']]()
    
    if not 'query_results' in context:
        context['query_results'] = ""

    #Here we add data from the previous system timer, and pass it to the view via context dictionary
    InNmap = sdService({"name":"vdinnmap"})
    InNmap.read()
    InNmap.setContext(context)
    
    ensure_dirs("/opt/asf/toolsrun/nmap.int/reports")
    page = 0
    page_size = GENERAL_PAGE_SIZE
    if 'page' in request.POST:
        page = int(request.POST['page'])
    
    ResultsExclude = ""
    if 'results_exclude' in request.POST:
        ResultsExclude=request.POST['results_exclude']
        context['results_exclude'] = ResultsExclude

    if 'results_search' in request.POST:
        ResultsSearch=request.POST['results_search']
        context['query_results'] = search(ResultsSearch, 'inservices', ResultsExclude)
        context['query_count'] = context['query_results'].count() 
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
        context['results_search'] = ResultsSearch
        context['show_save'] = True
    else:
        context['query_results'] = vdInServices.objects.all()
        context['query_count'] = context['query_results'].count()
        slicer = pager(context, page, page_size, context['query_count'])
        context['query_results'] = context['query_results'][slicer]
        context['show_save'] = False
    context['saved_regexp'] = vdRegExp.objects.all()[0:3000]
    context['query_results'] = host_picture(context['query_results'])
        
    if path.isfile("/opt/asf/toolsrun/nmap.int/reports/nmap.lock"):
        context['running'] = True
    else:
        context['running'] = False

    logger.debug(f"context {context} for action {request.POST}")
    html_template = loader.get_template( 'vd-in-portscan.html' )
    return HttpResponse(html_template.render(context, request))
    #return HttpResponseRedirect(html_template.render(context, request))

@login_required(login_url="/login/")
def redteam(request):
    context = {}
    context['segment'] = 'vd-redteam'
    def detect_modules():
        today = date.today()
        tstring = today.strftime("%m/%d/%y")
        modules = []
        MODULE_FOLDER = "/opt/asf/redteam/"
        for inode in sorted(os.listdir(MODULE_FOLDER)):
            if path.isdir(MODULE_FOLDER+inode):
                if path.exists(MODULE_FOLDER+inode+"/start"):
                    info = "Info File not found on "+inode
                    if path.exists(MODULE_FOLDER+inode+"/info"):
                        info_file = open(MODULE_FOLDER+inode+"/info", "r")
                        info = info_file.readline(250)
                        info.rstrip("\n")
                        info_file.close()
                    modules.append({"name":inode, "last_report":tstring, "current_report":tstring, "info":info})
        #Below line was used when the program did not complete
        #modules.append({"name":"wget", "last_report":tstring, "current_report":tstring, "info":"This is an example2"})
        return modules
    
    def detect_running_jobs(JobsArray):
        RunningJobs = {}
        #sys.stderr.write("\n\n\n"+str(JobsArray)+"\n\n\n")
        for Job in JobsArray:
            #sys.stderr.write(str(Job)+"\n\n\n")
            if path.exists("/opt/asf/jobs/"+str(Job.id)+"/.lock"):
                RunningJobs[Job.id] = True
        return RunningJobs
    
    def retrieve_metadata(JobsArray):
        #This function suddnely does much more than detect reports, also pass it trough cmdargs and scheduling, there is no way to split it in other functions
        #Perhaps a proper clear way should be changing the name of this function, populate_info, or retrieve_current_info, or something like that
        NUMERICAL_REGEXP = re.compile("[0-9]*")
        REPORT_REGEXP = ["**/*.[tT][xX][tT]", "**/*.[hH][tT][mM][lL]*", "**/*.[cC][sS][vV]", "**/*.[nN][mM][aA][pP]"] 
        REPORT_EXCLUDE = ['slice']
        CMDARG_REGEXP = re.compile("\d+\.cmdarg")
        JOBS_FOLDER = "/opt/asf/jobs/"
        REPORTS = {}
        NEW_JOBS_ARRAY = []
        for Job in JobsArray:
            JOB_REPORTS = []
            JOB_CMDARGS = []
            JOB_FOLDER = JOBS_FOLDER+str(Job.id)+"/"
            JOB_MODULE = "/opt/asf/redteam/"+Job.module+"/"
            #sys.stderr.write(JOB_FOLDER+"\n")
            if path.exists(JOB_FOLDER):
                for inode in sorted(os.listdir(JOB_FOLDER)):
                    if path.isdir(JOB_FOLDER+inode) and NUMERICAL_REGEXP.match(JOB_FOLDER+inode):
                        #sys.stderr.write(inode+"\n")
                        for pattern in REPORT_REGEXP:
                            for recursive_inode in pathlib.Path(JOB_FOLDER+inode).glob(pattern):
                                FCOMP = "jobs/"+str(Job.id)+"/"+inode+"/"+str(recursive_inode).rsplit("/"+inode+"/", 4)[1]
                                # FCOMP = "/static/jobs/"+str(Job.id)+"/"+inode+"/"+str(recursive_inode).rsplit("/"+inode+"/", 4)[1]
                                EXCLUDE_FLAG = False
                                for EXCLUDE in REPORT_EXCLUDE:
                                    if EXCLUDE in FCOMP:
                                        EXCLUDE_FLAG = True
                                if not EXCLUDE_FLAG:
                                    JOB_REPORTS.append({'name':inode, 'file':FCOMP})
                                    #sys.stderr.write(str(recursive_inode)+":"+FCOMP+"\n")
            HINTTXT = ""
            if path.exists(JOB_MODULE):
                sys.stderr.write(JOB_MODULE+"\n")
                for inode in sorted(os.listdir(JOB_MODULE)):
                    #sys.stderr.write(inode+"\n")
                    if path.isfile(JOB_MODULE+inode) and CMDARG_REGEXP.match(inode):
                        #sys.stderr.write("Match:"+inode+"\n")
                        NARG = NUMERICAL_REGEXP.findall(inode)[0]
                        #Handling the override by Job
                        if path.isfile(JOB_FOLDER+inode):
                            ARGFILE = open(JOB_FOLDER+inode,'r')
                        else:
                            ARGFILE = open(JOB_MODULE+inode,'r')

                        ARGCONTENT = ARGFILE.read().rstrip()
                        ARGFILE.close()
                        JOB_CMDARGS.append({'name':NARG, 'arg':ARGCONTENT})
                if path.isfile(JOB_MODULE+"hint.cmdarg"):
                    HINT = open(JOB_MODULE+"hint.cmdarg",'r')
                    HINTTXT = HINT.read().rstrip()
                    HINT.close()

            MSF_DATA = {}
            if Job.module == "metasploit":
                MSF_DATA = metasploit_read_args(Job)
            #Here we add data from the previous system timer, and pass it to the view via context dictionary
            JobSchInfo = {}
            JobSch = sdService({"name":"vdjob"+str(Job.id)})
            JobSch.read()
            JobSch.setContext(JobSchInfo)
            
            NEW_JOBS_ARRAY.append({'id':Job.id, 'name':Job.name, 'regexp':Job.regexp, 'exclude':Job.exclude, 'input':Job.input, 'info':Job.info, 'module':Job.module, 'reports':JOB_REPORTS, 'cmdargs':JOB_CMDARGS, 'hint':HINTTXT, 'Days':JobSchInfo['Days'], 'Disabled':JobSchInfo['Disabled'], 'Hour':JobSchInfo['Hour'], 'Minute':JobSchInfo['Minute'], 'Repeat':JobSchInfo['Repeat'], 'DaysOfWeek':JobSchInfo['DaysOfWeek'], 'msf':MSF_DATA})
        #sys.stderr.write(str(NEW_JOBS_ARRAY))
        return NEW_JOBS_ARRAY

    def job_save_cmdargs():
        JOBS_FOLDER = "/opt/asf/jobs/"
        if 'job_id' in request.POST:
            job_id = request.POST['job_id']
        else:
            sys.stderr.write("Error: No JobID from View redteam\n")
            return
        for n in range(0,9):
            ARG = str(n)
            if ARG in request.POST:
                cmdarg = request.POST[ARG]
                FILENAME = JOBS_FOLDER+job_id+"/"+ARG+".cmdarg"
                JOB_FOLDER = JOBS_FOLDER+job_id
                ensure_dirs(JOB_FOLDER)
                FILEARG = open(FILENAME, 'w+')
                sys.stderr.write("Writing:"+FILENAME+"\n")
                FILEARG.write(cmdarg)
                FILEARG.close()
        return True
       
    def job_create():
        if 'job_name' in request.POST:
            job_name = request.POST['job_name']
        else:
            job_name = "Default"
            
        if 'job_input' in request.POST:
            job_input = request.POST['job_input']
        else:
            job_input = "Unknown"
        # job_regexp = "Not Found"
        # job_exclude = "Error"
        # job_info = "Not Found"
        # setting default regexp to get all details
        job_regexp = ".*"
        job_exclude = ""
        job_info = "Default"
        try:
            jre = request.POST['job_regexp']
            qre = vdRegExp.objects.filter(id = jre).first()
            job_regexp = qre.regexp
            job_exclude = qre.exclude
            job_info = qre.info
        except:
            pass
            # job_regexp = "Not Found"
            # job_exclude = "Error"
            # job_info = "Error on searching RegExp Module"
            
        job_module = request.POST['job_module']
        try:
            NewJob = vdJob(name = job_name, regexp = job_regexp, exclude = job_exclude, module = job_module, input = job_input, info = job_info)
            NewJob.save()
            return True
        except:
            sys.stderr.write("Duplicate Job:"+job_name)
            context['error'] = "There was an error creating new Job"
        return False

    def job_delete():
        if 'job_id' in request.POST:
            job_id = request.POST['job_id']
            JobSch = sdService({'name':'vdjob'+job_id})
            JobSch.remove()
            try:
                RemoveJob = vdJob.objects.filter(id = job_id)
                RemoveJob.delete()
                return True
            except:
                sys.stderr.write("Inexistent or Already Deleted:"+jstr(ob_id))
                context['error'] = "There was an error deleting the Job"
        return False
    
    def job_start():
        logger.debug(f"inside red team job_start")
        if 'job_id' in request.POST:
            job_id = request.POST['job_id']
            logger.debug(f"with job_start job id {job_id}")
            Job = vdJob.objects.filter(id = job_id)[0]
            JOB_FOLDER = "/opt/asf/jobs/"+str(job_id)+"/"
            ensure_dirs(JOB_FOLDER)
            ensure_dirs("/opt/asf/hosts/")
            MODULE_FOLDER = "/opt/asf/redteam/"+Job.module+"/"
            logger.debug(f"module folder {MODULE_FOLDER}")
            try:
                if not path.exists("/opt/asf/frontend/asfui/core/static/jobs"):
                    os.symlink("/opt/asf/jobs","/opt/asf/frontend/asfui/core/static/jobs")
                if not path.exists("/opt/asf/frontend/asfui/core/static/hosts"):
                    os.symlink("/opt/asf/hosts","/opt/asf/frontend/asfui/core/static/hosts")

                if path.exists(MODULE_FOLDER+"start"):
                    #Lock file has to be created by module, good to remove it on termination or kill
#                     lockfile = open(JOB_FOLDER+".lock","w+")
#                     lockfile.write(job_id)
#                     lockfile.close()
                    # subprocess.Popen(["nohup", MODULE_FOLDER+"start",str(job_id)], cwd=JOB_FOLDER)
                    subprocess.Popen(["/bin/bash", MODULE_FOLDER+"start",str(job_id)], cwd=JOB_FOLDER)
                    #Out of scope - do not try 
                    #context['running_jobs'][job_id] = True
                    time.sleep(5)
                else:
                    msg = "Error in module: "+Job.module+" not functional, missing start or stop\n"
                    sys.stderr.write(msg)
                    context['error'] = msg
                    return False
                    
            except Exception as e:
                sys.stderr.write("Error Starting the job:"+str(job_id)+"\n"+str(e))
        return True
    
    def job_stop():
        if 'job_id' in request.POST:
            job_id = request.POST['job_id']
            Job = vdJob.objects.filter(id = job_id)[0]
            JOB_FOLDER = "/opt/asf/jobs/"+str(job_id)+"/"
            MODULE_FOLDER = "/opt/asf/redteam/"+Job.module+"/"
            try:
                if not path.exists("/opt/asf/frontend/asfui/core/static/jobs"):
                    os.symlink("/opt/asf/jobs","/opt/asf/frontend/asfui/core/static/jobs")
                if path.exists(MODULE_FOLDER+"stop"):
                    subprocess.Popen(["/bin/bash", MODULE_FOLDER+"stop",str(job_id)], cwd=JOB_FOLDER)
                    #Giving 10 seconds to stop
                    time.sleep(10)
                else:
                    subprocess.Popen(["nohup", "/opt/asf/tools/scripts/stop",str(job_id)], cwd=JOB_FOLDER)
                    #Giving 10 seconds to stop
                    time.sleep(10)
                    msg = "Using default Script stop: "+Job.module+" not functional, missing stop\n"
                    sys.stderr.write(msg)
                    context['error'] = msg
                    
            except Exception as e:
                sys.stderr.write("Error Starting the job:"+str(job_id)+"\n"+str(e))
        return True

    def job_schedule():
        if 'job_id' in request.POST:
            job_id = request.POST['job_id']
            Job = vdJob.objects.filter(id = job_id)[0]
            JOB_FOLDER = "/opt/asf/jobs/"+str(job_id)+"/"
            ensure_dirs(JOB_FOLDER)
            ensure_dirs("/opt/asf/hosts/")
            MODULE_FOLDER = "/opt/asf/redteam/"+Job.module+"/"
            try:
                if not path.exists("/opt/asf/frontend/asfui/core/static/jobs"):
                    os.symlink("/opt/asf/jobs","/opt/asf/frontend/asfui/core/static/jobs")
                if not path.exists("/opt/asf/frontend/asfui/core/static/hosts"):
                    os.symlink("/opt/asf/hosts","/opt/asf/frontend/asfui/core/static/hosts")

                if path.exists(MODULE_FOLDER+"start"):
                    ExecStart = MODULE_FOLDER+"start "+str(job_id)
                else:
                    ExecStart = "/bin/false"
                    
            except Exception as e:
                sys.stderr.write("Error preparing the job:"+str(job_id)+"\n"+str(e))

        JobSch = sdService({"name":"vdjob"+job_id})
        JobSch.readTimerFromRequest(request)
        JobSch.config['Unit']['Description'] = "Attack Surface Framework Internal Job Service File For Job "+job_id
        JobSch.config['Unit']['Requires'] = "docker.service"
        JobSch.config['Service']['ExecStart'] = ExecStart 
        JobSch.write()
        return
    
    def metasploit_save_args():
        if 'job_id' in request.POST:
            job_id = request.POST['job_id']
            JOB_FOLDER = "/opt/asf/jobs/"+str(job_id)+"/"
            ensure_dirs(JOB_FOLDER)
            return msf_save_args(request)
        return False

    def metasploit_read_args(Job):
        JOB_FOLDER = "/opt/asf/jobs/"+str(Job.id)+"/"
        ensure_dirs(JOB_FOLDER)
        return msf_read_args(Job)
        
    def metasploit_read_modules():
        MSF_LIST = ["/opt/asf/redteam/metasploit/el.txt", "/opt/asf/redteam/metasploit/al.txt"]
        EL = []
        for FILE in MSF_LIST:
            MSFE = open(FILE, "r")
            for line in MSFE:
                 EL.append(line.rstrip())
        return EL

    def return_report_file():
        logger.debug("return_report file")
        if 'report_file' in request.POST:
            if 'job_id' in request.POST:
                job_id = request.POST['job_id']
                logger.debug(f"with job_start job id {job_id}")
                Job = vdJob.objects.filter(id = job_id)[0]
                JOB_FOLDER = "/opt/asf/"
                ensure_dirs(JOB_FOLDER)
                report_name = JOB_FOLDER + request.POST['report_file']
                logger.debug(f"return_report fiile {report_name}")
                f = open(report_name, 'r')
                file_content = f.read()
                f.close()
                # return HttpResponse(file_content, content_type="text/plain")
                # logger.debug(f"file content {file_content}")
                return file_content

    logger.debug(f"inside vd-redteam request {request.POST}")
    file_content_read = None
    action={'create':job_create, 'delete':job_delete, 'start':job_start, 'stop':job_stop, 'save_cmdargs':job_save_cmdargs, 'schedule':job_schedule, 'msf_save':metasploit_save_args}
    if 'job_action' in request.POST:
        if request.POST['job_action'] in action:
            action[request.POST['job_action']]()   
        elif 'report_file'in request.POST['job_action']: 
            file_content_read = return_report_file ()

    context['saved_regexp'] = vdRegExp.objects.all()
    context['jobs'] = vdJob.objects.all()
    context['running_jobs'] = detect_running_jobs(context['jobs'])
    context['jobs'] = retrieve_metadata(context['jobs'])
    logger.debug(f"jobs metadata {context['jobs']}")
    logger.debug(f"running jobs {context['running_jobs']}")
    # logger.debug(f"file content {file_content_read}")
    context['modules'] = detect_modules()
    context['msf_modules'] = metasploit_read_modules()
    if file_content_read:
        context['file_content'] = file_content_read
    
    html_template = loader.get_template( 'vd-redteam.html' )
    # if file_content_read:
    #     return HttpResponse(html_template.render(context, request, content_type="application/json"))
    # else:
    return HttpResponse(html_template.render(context, request))
    
@login_required(login_url="/login/")
def index(request):
    
    context = {}
    context['segment'] = 'index'

    html_template = loader.get_template( 'index.html' )
    return HttpResponse(html_template.render(context, request))

@login_required(login_url="/login/")
def export(request):
# Create the HttpResponse object with the appropriate CSV header.
    def export_amass(writer):
        query = vdResult.objects.all()
        writer.writerow(['name', 'type', 'ipv4', 'lastdate', 'tag', 'info'])
        for host in query:
            writer.writerow([host.name, host.asset_type, host.ipv4, host.lastdate, host.tag, host.info])
        return
    
    def export_services(writer):
        regexp = ""
        exclude = ""
        if 'regexp_id' in request.POST:
            try:
                jre = request.POST['regexp_id']
                qre = vdRegExp.objects.filter(id = jre).first()
                regexp = qre.regexp
                exclude = qre.exclude
            except:
                sys.stderr.write("Error looking for the regular expression\n")
                
        query = search(regexp, 'services', exclude)
        writer.writerow(['name', 'cname', 'ipv4', 'lastdate', 'ports', 'full_ports', 'service_ssh', 'service_rdp', 'service_telnet', 'service_ftp', 'service_smb', 'nuclei_http', 'owner', 'tag', 'metadata'])
        for host in query:
            writer.writerow([host.name, host.nname, host.ipv4, host.lastdate, host.ports, host.full_ports, host.service_ssh, host.service_rdp, host.service_telnet, host.service_ftp, host.service_smb, host.nuclei_http, host.owner, host.tag, host.metadata])
        return

    def export_inservices(writer):
        regexp = ""
        exclude = ""
        if 'regexp_id' in request.POST:
            try:
                jre = request.POST['regexp_id']
                qre = vdRegExp.objects.filter(id = jre).first()
                regexp = qre.regexp
                exclude = qre.exclude
            except:
                sys.stderr.write("Error looking for the regular expression\n")
                
        query = search(regexp, 'inservices', exclude)
        writer.writerow(['name', 'cname', 'ipv4', 'lastdate', 'ports', 'full_ports', 'service_ssh', 'service_rdp', 'service_telnet', 'service_ftp', 'service_smb', 'nuclei_http', 'owner', 'tag', 'metadata'])
        for host in query:
            writer.writerow([host.name, host.nname, host.ipv4, host.lastdate, host.ports, host.full_ports, host.service_ssh, host.service_rdp, host.service_telnet, host.service_ftp, host.service_smb, host.nuclei_http, host.owner, host.tag, host.metadata])
        return
    
    def export_targets(writer):
        query = vdTarget.objects.all()
        writer.writerow(['name', 'type', 'lastdate', 'itemcount', 'tag', 'owner', 'metadata'])
        for host in query:
            writer.writerow([host.name, host.asset_type, host.lastdate, host.itemcount, host.tag, host.owner, host.metadata])
        return

    def export_intargets(writer):
        query = vdInTarget.objects.all()
        writer.writerow(['name', 'type', 'lastdate', 'itemcount', 'tag', 'owner', 'metadata'])
        for host in query:
            writer.writerow([host.name, host.asset_type, host.lastdate, host.itemcount, host.tag, host.owner, host.metadata])
        return

    def export_nuclei(writer):
        query = vdNucleiResult.objects.all()
        writer.writerow(['name', 'type', 'tfp', 'lastdate', 'vulnerability', 'info', 'full_uri', 'metadata'])
        for host in query:
            writer.writerow([host.name, host.asset_type, host.tfp, host.lastdate, host.vulnerability, host.info, host.full_uri, host.metadata])
        return
        
    def export_cypher_ex(writer):
        return export_cypher(writer,'services')
    
    def export_cypher_in(writer):
        return export_cypher(writer,'inservices')
        
    def export_cypher(writer,service_mode):
        regexp = ""
        exclude = ""
        if 'regexp_id' in request.POST:
            try:
                jre = request.POST['regexp_id']
                qre = vdRegExp.objects.filter(id = jre).first()
                regexp = qre.regexp
                exclude = qre.exclude
            except:
                sys.stderr.write("Error looking for the regular expression\n")
                
        query = search(regexp, service_mode, exclude)
        
        ByLEVEL = []
        for i in range(5):
            ByLEVEL.append([])
        
        def subdomain(DARRAY, DOMAIN):
            #global ByLEVEL
            if DOMAIN.count(".")>1:
                DPARTS = DOMAIN.split(".")
                PDOM = ""
                PC = -1
                sys.stderr.write("DPARTS:"+str(len(DPARTS))+"\n")
                for PART in DPARTS[::-1]:
                    PC+=1
                    if PC==0:
                        PDOM = PART
                        if PDOM not in ByLEVEL[0]:
                            ByLEVEL[0].append(PDOM)
                        continue
                    PDOM = PART+"."+PDOM
                    if PC==1:
                        if PDOM not in ByLEVEL[1]:
                            ByLEVEL[1].append(PDOM)
                            sys.stderr.write("Extra Domain By Level"+str(PC)+": "+PDOM+"\n")
                        if PDOM not in DARRAY:
                            DARRAY.append(PDOM)
                            sys.stderr.write("Extra Domain"+str(PC)+": "+PDOM+"\n")
                        continue
                    if PC <=4 and PC >=2:
                        sys.stderr.write("PartCount for Other Level:"+str(PC)+" \n")
                        if PDOM not in ByLEVEL[PC]:
                            ByLEVEL[PC].append(PDOM)
                    if PC>1:
                        #If there are more than 3 dots, skip to the next row
                        if PDOM.count(".")>2:
                            DO = "NOTHING"
                            #break;
                        else:
                            if PDOM not in DARRAY:
                                DARRAY.append(PDOM)
                                sys.stderr.write("Extra Domain: "+PDOM+"\n")
            return

        DNAME = []
        IPADDR = []
        SERVICES = []
        NUCLEI = []
        for row in query:
            sys.stderr.write(str(row)+"\n")
            #0=Domain Requested
            if not row.name in DNAME:
                DNAME.append(row.name)
                subdomain(DNAME,row.name)
            #1=Domain Redirected to (CNAME)
            if row.nname not in DNAME:
                DNAME.append(row.nname)
                subdomain(DNAME,row.nname)
            #2=IP Address
            if row.ipv4 not in IPADDR:
                IPADDR.append(row.ipv4)
            #5=Full List of Ports
            PSERVICES = row.full_ports.split(", ")
            for PSERVICE in PSERVICES:
                if PSERVICE not in SERVICES:
                    SERVICES.append(PSERVICE)
                    sys.stderr.write("New Service Found:"+PSERVICE+"\n")
            #11=Nuclei
            if not row.nuclei_http.strip() == "":
                NLINES = row.nuclei_http.split("\n")
                for NLINE in NLINES:
                    NLINE = NLINE.replace("\"", "")
                    if NLINE not in NUCLEI:
                        NUCLEI.append(NLINE)
                          
        sys.stderr.write(str(DNAME)+"\n")
        sys.stderr.write(str(IPADDR)+"\n")
        sys.stderr.write(str(SERVICES)+"\n")
        sys.stderr.write(str(NUCLEI)+"\n")
        
        for item in DNAME:
            writer.write("CREATE (:DOMAIN {name:\""+item+"\"});\n")
        for item in IPADDR:
            writer.write("CREATE (:IPADDR {ip:\""+item+"\"});\n")
        for item in SERVICES:
            writer.write("CREATE (:SERVICE {psh:\""+item+"\"});\n")
        for item in NUCLEI:
            writer.write("CREATE (:NUCLEI {info:\""+item+"\"});\n")
        #Reopen the file to create relationships
        for row in query:
            sys.stderr.write(str(row)+"\n")
            #writer.writerow(['name', 'cname', 'ipv4', 'lastdate', 'ports', 'full_ports', 'service_ssh', 'service_rdp', 'service_telnet', 'service_ftp', 'service_smb', 'nuclei_http'])
            if row.nname.strip() == "":
                #1=CNAME, empty means no redirection, using only 0
                #2=Ipaddr
                writer.write("MATCH (d:DOMAIN {name:\""+row.name+"\"}) MATCH (i:IPADDR {ip: \""+row.ipv4+"\"}) CREATE (d)-[:RESOLVE]->(i);\n")
            else:
                #1=CNAME, not empty means redirection, using 1 and 0->1
                #2=Ipaddr
                writer.write("MATCH (d:DOMAIN {name:\""+row.nname+"\"}) MATCH (i:IPADDR {ip: \""+row.ipv4+"\"}) CREATE (d)-[:RESOLVE]->(i);\n")
                writer.write("MATCH (d:DOMAIN {name:\""+row.name+"\"}) MATCH (c:DOMAIN {name: \""+row.nname+"\"}) CREATE (d)-[:REDIRECTS]->(c);\n")
            
            #11=Nuclei
            if not row.nuclei_http.strip() == "":
                NLINES = row.nuclei_http.split("\n")
                for NLINE in NLINES:
                    NLINE = NLINE.replace("\"", "")
                    writer.write("MATCH (d:IPADDR {ip:\""+row.ipv4+"\"}) MATCH (n:NUCLEI {info: \""+NLINE+"\"}) CREATE (d)-[:HAS]->(n);\n")
            #5=Ipaddr
            PSERVICES = row.full_ports.split(", ")
            for PSERVICE in PSERVICES:
                writer.write("MATCH (i:IPADDR {ip:\""+row.ipv4+"\"}) MATCH (s:SERVICE {psh: \""+PSERVICE+"\"}) CREATE (i)-[:PROVIDES]->(s);\n")
            
        return
    
    response = HttpResponse(content_type='text/csv')
    writer = csv.writer(response, delimiter='\t')
    export_model={'amass':export_amass, 'services':export_services, 'inservices':export_inservices, 'targets':export_targets, 'intargets':export_intargets, 'nuclei':export_nuclei}
    export_cypher_model={'services_cypher':export_cypher_ex, 'inservices_cypher':export_cypher_in}
    if 'model' in request.POST:
        model = request.POST['model']
        sys.stderr.write(model+'\n')
        if model in export_model:
            response['Content-Disposition'] = 'attachment; filename="'+model+'.tsv"'
            export_model[model](writer)
    
        if model in export_cypher_model:
            response['Content-Disposition'] = 'attachment; filename="'+model+'.cypher"'
            export_cypher_model[model](response)
            
    return response

@login_required(login_url="/login/")
def pages(request):

    context = {}
    # All resource paths end in .html.
    # Pick the html file name from the url. And load template.
    try:
        
        load_template      = request.path.split('/')[-1]
        context['segment'] = load_template
        html_template = loader.get_template( load_template )
        return HttpResponse(html_template.render(context, request))
        
    except template.TemplateDoesNotExist:

        html_template = loader.get_template( 'page-404.html' )
        return HttpResponse(html_template.render(context, request))

    except:
    
        html_template = loader.get_template( 'page-500.html' )
        return HttpResponse(html_template.render(context, request))
    