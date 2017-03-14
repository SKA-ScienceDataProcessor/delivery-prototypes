#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Main function and global init routines for transfer service prototype."""
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

from __future__ import print_function  # for python 2

import ConfigParser
import logging
import sys
import time
import twisted

from OpenSSL import crypto, SSL
from OpenSSL.crypto import X509StoreFlags
from os.path import dirname, exists, expanduser, join, realpath
from pika import ConnectionParameters
from pika.adapters.twisted_connection import TwistedProtocolConnection
from time import localtime, strftime
from twisted.enterprise import adbapi
from twisted.internet import defer, endpoints, protocol, reactor, ssl
from twisted.internet._sslverify import CertBase
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import ClientCreator
from twisted.logger import FileLogObserver, formatEvent, \
                           globalLogPublisher, Logger
from twisted.web.resource import Resource
from twisted.web.server import Site

# The web pages
from rootpage import RootPage
from stagingfinish import StagingFinish
from transfersubmit import TransferSubmit
from transferstatus import TransferStatus

# FTS and Staging backends
from staging import init_staging
from ftsmanager import init_fts_manager

# Util methods
from util import load_allowed_DNs

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


def main():
    """Main function for transfer service prototype.

    This function:
    * initializes connections to database and RabbitMQ
    * sets up the web interface linkage
    * calls staging and FTS initialization routines
    * listens on the desired port
    * ... and finally, starts reactor
    """
    log = Logger()
    observer = FileLogObserver(sys.stdout, lambda x: formatEvent(x) + "\n")
    globalLogPublisher.addObserver(observer)
    log.info("Initialized logging")
    twisted.python.log.startLogging(sys.stdout)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    # Load settings
    cfg_file = expanduser('~/.transfer.cfg')
    if not exists(cfg_file):
        cfg_file = join(dirname(realpath(__file__)), 'transfer.cfg')
    log.debug("Loading config from {0}".format(cfg_file))
    configData = ConfigParser.ConfigParser()
    configData.read(cfg_file)

    # Establish DB connection
    dbpool = adbapi.ConnectionPool('MySQLdb',
                                   host=configData.get('mysql', 'hostname'),
                                   user=configData.get('mysql', 'username'),
                                   passwd=configData.get('mysql', 'password'),
                                   db=configData.get('mysql', 'db'))
    log.info("DB Connection Established")

    # Retrieve values needed for rabbit mq connections
    staging_queue = configData.get('amqp', 'staging_queue')
    transfer_queue = configData.get('amqp', 'transfer_queue')
    pika_hostname = configData.get('amqp', 'hostname')

    # Create root webpage
    root = RootPage()
    root.putChild('', root)

    def _setupApp(pika_conn):
        # Add child web pages
        t_submit = TransferSubmit(dbpool, staging_queue, pika_conn)
        root.putChild('submitTransfer', t_submit)
        root.putChild('transferStatus', TransferStatus(dbpool))
        root.putChild('doneStaging', StagingFinish(dbpool))

        # Setup staging manager
        staging_concurrent_max = configData.get('staging', 'concurrent_max')
        staging_url = configData.get('staging', 'server')
        staging_callback = configData.get('staging', 'callback')
        init_staging(pika_conn, dbpool, staging_queue, staging_concurrent_max,
                     staging_url, staging_callback, transfer_queue)

        # Setup FTS manager
        fts_concurrent_max = configData.get('fts', 'concurrent_max')
        fts_params = [
                      configData.get('fts', 'server'),  # URI of FTS service
                      configData.get('fts', 'cert'),  # cert
                      configData.get('fts', 'key')  # key
                     ]
        fts_interval = configData.get('fts', 'polling_interval')
        init_fts_manager(pika_conn, dbpool, fts_params, transfer_queue,
                         fts_concurrent_max, fts_interval)

    # Setup pika connection
    pika_cc = ClientCreator(reactor, TwistedProtocolConnection,
                            ConnectionParameters())
    d = pika_cc.connectTCP(pika_hostname, 5672)
    d.addCallback(lambda protocol: protocol.ready)
    d.addCallback(_setupApp)

    # Create factory for site
    factory = Site(root)

    # Setup HTTP
    endpoint = endpoints.TCP4ServerEndpoint(reactor, 8080,
                                            interface='127.0.0.1')
    endpoint.listen(factory)

    # Setup SSL
    def _load_cert_function(x):
        return crypto.load_certificate(crypto.FILETYPE_PEM, x)
    ssl_cert = configData.get('ssl', 'cert')
    ssl_key = configData.get('ssl', 'key')
    ssl_trust_chain = configData.get('ssl', 'chain')
    ctx_opt = {}
    with open(ssl_cert, 'r') as f:
        ctx_opt['certificate'] = _load_cert_function(f.read())
    with open(ssl_key, 'r') as f:
        ctx_opt['privateKey'] = crypto.load_privatekey(crypto.FILETYPE_PEM,
                                                       f.read())
    with open(ssl_trust_chain, 'r') as f:
        certchain = []
        for line in f:
            if '-----BEGIN CERTIFICATE-----' in line:
                certchain.append(line)
            else:
                certchain[-1] = certchain[-1] + line
    certchain_objs = map(_load_cert_function, certchain)
    ctx_opt['extraCertChain'] = certchain_objs
    ctx_opt['enableSingleUseKeys'] = True
    ctx_opt['enableSessions'] = True

    # Note that Ubuntu doesn't necessarily install CA certificates properly
    # If following the recommended process (add CA cert with .crt extension
    # to /usr/local/share/ca-certificates, run "sudo update-ca-certificates")
    # that this is inadequate.  The certificate is added with a .pem extension
    # but OpenSSL only detects it with a .0 extension.  The Grid Canada CA
    # also produces two files with c_rehash is run, whereas
    # update-ca-certificates only added one
    ctx_opt['trustRoot'] = ssl.OpenSSLDefaultPaths()

    ssl_ctx_factory = ssl.CertificateOptions(**ctx_opt)

    # By default the SSL context factory doesn't support the use of X.509 proxy
    # certificates. This must be enabled by setting a flag using a few methods.
    ssl_context = ssl_ctx_factory.getContext()
    ssl_cert_store = ssl_context.get_cert_store()
    ssl_cert_store.set_flags(X509StoreFlags.ALLOW_PROXY_CERTS)

    # Load a list of X.509 distinguished names which will grant access to
    # the system
    print(configData.get('auth', 'permitted'))
    load_allowed_DNs(configData.get('auth', 'permitted'))

    sslendpoint = endpoints.SSL4ServerEndpoint(reactor, 8443,
                                               ssl_ctx_factory)
    sslendpoint.listen(factory)

    reactor.run()

if __name__ == '__main__':
    main()
