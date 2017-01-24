#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2016  University of Cape Town
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function # for python 2

__author__ = "David Aikema, <david.aikema@uct.ac.za>"

import fts3.rest.client.easy as fts3
import os
import sys
import time

# Python Easy bindings documents for FTS
# http://fts3-docs.web.cern.ch/fts3-docs/fts-rest/docs/easy/index.html
# additional docs for submitting transfers:
# http://fts3-docs.web.cern.ch/fts3-docs/fts-rest/docs/easy/submit.html
#
# note that you can setup additional sources, modify priorities, change how job IDS are
# assigned, etc.  Not sure if the job ID only allows you to choose from one of several
# options or if this can be made pretty arbitrary - e.g. adding in things like SKA
# project IDs or some such thing
if 'X509_USER_PROXY' not in os.environ:
  print ('X509_USER_PROXY must be defined in your environment')
  sys.exit()

endpoint = 'https://fts1.cyberska.org:8446'

try:
  context = fts3.Context(endpoint)
except Exception, e:
  print (str(e))
  sys.exit()

# print out whoami info
#print (fts3.whoami(context))

src = 'gsiftp://ubuntu@deliv-prot1.cyberska.org/bin/bash'
dst = 'gsiftp://ubuntu@deliv-prot2.cyberska.org/home/ubuntu/bin-bash-easy'
src2 = 'gsiftp://ubuntu@deliv-prot1.cyberska.org/etc/services'
dst2 = 'gsiftp://ubuntu@deliv-prot2.cyberska.org/home/ubuntu/etc-services-easy'

# Submit a transfer
transfer = fts3.new_transfer(src, dst)
transfer2 = fts3.new_transfer(src2, dst2)

job = fts3.new_job([transfer, transfer2])
job_id = fts3.submit(context, job)

job_status = fts3.get_job_status(context,job_id)
print (job_status)

# Check if job status is finished: job_status['job_state'] == 'FINISHED'

broken_dst = 'gsiftp://ubuntu@deliv-prot-invalid.cyberska.org/home/ubuntu/bin-bash-easy'
broken_transfer = fts3.new_transfer(src, broken_dst)

broken_job = fts3.new_job([broken_transfer])
broken_job_id = fts3.submit(context, broken_job)

job_state = 'INIT'
print ("Looping every 5 seconds until the broken job reports 'FAILED'")
while job_state != 'FAILED':
  print (job_state)
  job_status = fts3.get_job_status(context,broken_job_id)
  job_state = job_status['job_state']
  time.sleep(5)

print ("if you got here the broken job must have failed 'successfully'")