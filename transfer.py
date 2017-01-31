#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2017  University of Cape Town
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
#import json
#import os
import pika
import sys
import time

from OpenSSL import SSL, crypto
from os.path import realpath, dirname, join
#from pika import exceptions
from pika.adapters import twisted_connection
from twisted.enterprise import adbapi
from twisted.internet import defer, endpoints, protocol, reactor, ssl
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, returnValue
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
#from twisted.internet.task import LoopingCall
from twisted.logger import globalLogPublisher, FileLogObserver, formatEvent, Logger
#from twisted.python.modules import getModule
from twisted.web.resource import Resource
from twisted.web.server import Site #, NOT_DONE_YET

# The web pages
from rootpage import RootPage
from stagingfinish import StagingFinish
from transfersubmit import TransferSubmit
from transferstatus import TransferStatus

# From 
from staging import init_staging
from ftsmanager import init_fts_manager

class PIKAReconnectingClientFactory(ReconnectingClientFactory):

  def startedConnecting(self, conn):
    global log
    log.info('About to connect to rabbitmq')
  def buildProtocol(self, addr):
    global log
    log.info('Connected')
    self.resetDelay()
    p = pika.ConnectionParameters()
    tc = twisted_connection.TwistedProtocolConnection(p)
    return tc
  def clientConnectionLost(self, conn, reason):
    global log
    log.info('Lost connection to rabbitmq: ' + str(reason))
    ReconnectingClientFactory.clientConnectionLost(self, conn, reason)
  def clientConnectionFailed(self, conn, reason):
    global log
    log.info('Unable to connect to rabbitmq: ' + str(reason))
    ReconnectingClientFactory.clientConnectionLost(self, conn, reason)

def main ():
  global dbpool
  global log
  global configData

  log = Logger()
  log.info("About to initialize logging")
  observer=FileLogObserver(sys.stdout, lambda x: formatEvent(x) + "\n")
  globalLogPublisher.addObserver(observer)
  #log = Logger(observer=FileLogObserver(sys.stdout, lambda x: formatEvent(x) + "\n"))
  log.info("Initialized logging")

  # Load settings
  cfg_file = join(dirname(realpath(__file__)), 'transfer.cfg')
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
  #root = RootPage(log)
  root = RootPage()
  root.putChild('', root)
  
  # Retrieve values needed for rabbit mq connections
  host = configData.get('ampq', 'hostname')
  staging_queue = configData.get('ampq', 'staging_queue')
  transfer_queue = configData.get('ampq', 'transfer_queue')

  # Setup connection and initialize web interface and fts + staging managers
  def setup_nodes(conn):
    # Setup web interface portions
    t_submit = TransferSubmit(dbpool, staging_queue, conn)
    root.putChild('submitTransfer', t_submit)
    root.putChild('transferStatus', TransferStatus(dbpool))
    root.putChild('doneStaging', StagingFinish(dbpool))
    
    staging_concurrent_max = configData.get('staging', 'concurrent_max')
#     x = DeferredSemaphore(1)
#     d = x.acquire()
#     d.addCallback(lambda x: x.release)
#     d.addCallback(lambda _: log.info('Acquired semaphore'))
#     d.addErrback(lambda _: log.error('Semaphore error'))
    init_staging(conn, dbpool, staging_queue, staging_concurrent_max)
    fts_server = configData.get('fts', 'server')
    fts_proxy = configData.get('fts', 'proxy')
    fts_concurrent_max = configData.get('fts', 'concurrent_max')
    #init_fts_manager(conn, dbpool, fts_server, fts_proxy,
    #                 transfer_queue, fts_concurrent_max)

  parameters = pika.ConnectionParameters()
  cc = protocol.ClientCreator(reactor,
                              twisted_connection.TwistedProtocolConnection,
                              parameters)
  d = cc.connectTCP(host, 5672)
  #prcf = PIKAReconnectingClientFactory()
  #conn = reactor.connectTCP(host, 5672, prcf)
  #d = prcf.protocol.ready
  #setup_nodes(conn)
  d.addCallback(lambda protocol: protocol.ready)
  d.addCallback(setup_nodes)

  # Setup HTTP
  factory = Site(root)  
  endpoint = endpoints.TCP4ServerEndpoint(reactor, 8080, interface='127.0.0.1')
  endpoint.listen(factory)

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
  #ctx_opt['verify'] = True
  #ctx_opt['requireCertificate'] = False
  #ctx_opt['caCerts'] = ssl.OpenSSLDefaultPaths()
  #ssl_ctx_factory = ssl.CertificateOptions(**ctx_opt)
  #sslendpoint = endpoints.SSL4ServerEndpoint(reactor, 8443, ssl_ctx_factory)
  #sslendpoint.listen(factory)

  reactor.run()

if __name__ == '__main__':
  main()	
