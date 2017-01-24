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

import ConfigParser
import fts3.rest.client.easy as fts3
import os
import pika
import sys
import time

from OpenSSL import SSL, crypto
from pika import exceptions
from pika.adapters import twisted_connection
from twisted.enterprise import adbapi
from twisted.internet import defer, endpoints, protocol, reactor, ssl, task, threads
from twisted.internet.task import LoopingCall
from twisted.logger import FileLogObserver, formatEvent, Logger
from twisted.python.modules import getModule
from twisted.web.resource import Resource
from twisted.web.server import Site, NOT_DONE_YET


# Setup a root website
class RootPage (Resource):
  def render_GET(self, request):
    return "Transfer Service Prototype"

# API function fall: submitTransfer
# (submit a transfer)
class TransferSubmit (Resource):
  isLeaf = True
  def render_GET(self, request):
    #log.info(dir(request))
    return "Submit transfer request"


# API function fall: getStatus
# (allow users to query the results of their transfer request)
class TransferStatus (Resource):
  isLeaf = True
  def render_GET(self, request):
  	return "Get transfer status"

# API function fall: doneStaging
# (have the stager signal that a job has been staged to local disk)
class StagingFinish (Resource):
  isLeaf = True
  def render_GET(self, request):
    return "Staging is done"

# FTS Updater
# (scans FTS server at a regular interval, updating the status of pending tasks)
def FTSUpdater():
  pass

####
# Initialize the app
####

log = Logger(observer=FileLogObserver(sys.stdout, lambda x: formatEvent(x) + "\n"))
log.info("Initializing logging")

# Load settings
cfg_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'transfer.cfg')
log.debug("Loading config from {0}".format(cfg_file))
configData = ConfigParser.ConfigParser()
configData.read(cfg_file)

# Establish DB connection
dbpool = adbapi.ConnectionPool('MySQLdb',
                               host=configData.get('mysql', 'host'),
                               user=configData.get('mysql', 'username'),
                               passwd=configData.get('mysql', 'password'),
                               db=configData.get('mysql', 'db'))
log.info("DB Connection Established")

# Launch server
root = RootPage()
root.putChild('', root)
root.putChild('submitTransfer', TransferSubmit())
root.putChild('getStatus', TransferStatus())
root.putChild('doneStaging', StagingFinish())
factory = Site(root)  
#endpoint = endpoints.TCP4ServerEndpoint(reactor, 8080)
#endpoint.listen(factory)

# Setup SSL
ssl_cert = configData.get('ssl', 'cert')
ssl_key = configData.get('ssl', 'key')
ssl_trust_chain = configData.get('ssl', 'chain')
ctx_opt= {}
with open(ssl_cert, 'r') as f:
  ctx_opt['certificate'] = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
with open(ssl_key, 'r') as f:
  ctx_opt['privateKey'] = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
load_cert_function = lambda(x): \
  crypto.load_certificate(crypto.FILETYPE_PEM, x)
with open(ssl_trust_chain, 'r') as f:
  certchain = []
  for line in f:
    if '-----BEGIN CERTIFICATE-----' in line:
      certchain.append(line)
    else:
      certchain[-1] = certchain[-1] + line
certchain_objs = map(load_cert_function, certchain)
ctx_opt['extraCertChain'] = certchain_objs
ctx_opt['enableSingleUseKeys'] = True
ctx_opt['enableSessions'] = True
#ctx_opt['trustRoot'] = ssl.OpenSSLDefaultPaths()
ctx_opt['verify'] = True
ctx_opt['requireCertificate'] = False
ctx_opt['caCerts'] = ssl.OpenSSLDefaultPaths()
ssl_ctx_factory = ssl.CertificateOptions(**ctx_opt)
sslendpoint = endpoints.SSL4ServerEndpoint(reactor, 8443, ssl_ctx_factory)
sslendpoint.listen(factory)

reactor.run()
