# XSPM Extended Attack Surface based Security Posture Management

## Overview

For organizations tracking cost-to-attack as a security metric, it is critical to make sure different digital assets are continuously assessed to make sure the known exploits for vulnerabilities are addressed before a threat actor takes advantage of the same. In order to do that combining internal & external attack surface monitoring with automated assessment tools, can be helpful. New acronym coined by the security vendor industry for the same is, XSPM!

This repo forked from https://github.com/vmware-labs/attack-surface-framework and has made improvements for streamlined usage by organizations who are short staffed in InfoSec team.

Roadmap: https://github.com/users/prakashar11/projects/1

## Tenets

1. Inventory of assets (IP addresses, domains, code repo, SaaS applications) through automated discovery
2. Keep track of the active assets
3. Leverage assessment tools from https://github.com/projectdiscovery for assessing assets - for vulnerabilities in software packages, configuration; also use MITRE ATT&CK surface test tools
4. CISA KEV (known exploitable vulnerabilities catalog) as an input to priorities assessment
5. Automated opening or closing of findings generated from the assessment tools against an asset; use assement test id used by the assessment tool to determine whether a finding is closed/to be reopened
5. Target users: short staffed InfoSec teams which can perform assessment on a weekly/bi-weekly basis and take follow up remediations

## Workflow

1. Build docker image
2. `http://127.0.0.1:8080` - For ASF - user:youruser pass:yourpass (provided in initial setup)

### External facing assets

1. Discover active domains
2. Perform assessment
3. Review findings - mark false positive; review reopened finding

TODO: SaaS applications configuration check e.g., Google Workspace configuration CIS benchmark assessment

### Internal assets
1. Auto discover of active assets with IP address; discovery based on specific IP or CIDR range or wildcard
2. Inventory enumeration
3. Perform assessment
4. Review findings

## Using docker

1. Clone repo
2. dc-build.sh - builds the image
3. dc-compose up - starts the container
4. http://127.0.0.1:8080
5. Note: default superuser created with admin credentials; needs change 

Note: this is the dev Django webserver based deployment; nginx and gunicorn are yet to be enabled. Also shares same unix socket as that of host.

## Operations Notes

- Discovery - Module that runs the Amass process to discover publicly exposed assets, feel free to create your configuration file to setup your API keys https://github.com/OWASP/Amass/blob/master/examples/config.ini; same goes for subfinder
- Initiate active asset discovery for IP address with wildcard (without this discovery list, nmap enumeration won't work)
- Assets enumeration; quick (nmap ping sweep) or full enumeration setup regex if required
- Red team - Input to select 'internal enumeration' and select module & save job; can take assets that were enumerated through ping sweep
- Start job

Security (TODO)

ASF is not meant to be publicly exposed, assuming you install it on a cloud provider or even on a local instance, we recommend to access it using port forwarding through SSH, here is an example:

`ssh -i "key.pem" -L 8080:127.0.0.1:8080 user@yourhost` - For ASF GUI

### Credits

https://www.djangoproject.com/

https://github.com/creativetimofficial/material-dashboard-django

https://nmap.org/

https://github.com/OWASP/Amass

https://github.com/lanjelot/patator

https://github.com/FortyNorthSecurity/EyeWitness

https://github.com/projectdiscovery/nuclei

https://www.metasploit.com

https://www.graylog.org/products/open-source

https://github.com/wpscanteam/wpscan

https://github.com/vanhauser-thc/thc-hydra

https://nxlog.co/products/nxlog-community-edition

https://www.docker.com/