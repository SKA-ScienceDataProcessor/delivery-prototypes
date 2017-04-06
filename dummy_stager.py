#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A minimalist staging engine simulator.

This service performs X.509 authn/z of incoming requests but does not
allow for the status of current or past transfers to be queried.
"""
# Copyright 2017 University of Cape Town
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
import json
import os
import shutil
import string
import sys
import requests
import uuid

from klein import Klein
from OpenSSL import crypto
from os.path import dirname, exists, expanduser, join, realpath
from socket import gethostname as hostname
from twisted.internet import endpoints, reactor, ssl, threads
from twisted.internet.defer import inlineCallbacks
from twisted.python import log
from twisted.web.server import Site

__author__ = "David Aikema, <david.aikema@uct.ac.za>"

# Init Klein and logging
app = Klein()
log.startLogging(sys.stdout)

# Load config settings
cfg_file = expanduser('~/.dummy_stager.cfg')
if not exists(cfg_file):
    cfg_file = join(dirname(realpath(__file__)), 'dummy_stager.cfg')
configData = ConfigParser.ConfigParser()
configData.read(cfg_file)

# Little init script
staging_src_dir = configData.get('directories', 'source')
staging_dst_dir = configData.get('directories', 'destination')

# Endpoint settings
ssl_cert = configData.get('ssl', 'cert')
ssl_key = configData.get('ssl', 'key')
ssl_chain = configData.get('ssl', 'chain')
server_port = int(configData.get('endpoint', 'port'))

# Transfer credentials
stager_cert = configData.get('credentials', 'cert')
stager_key = configData.get('credentials', 'key')

# Get list of DNs allowed access
config_dns = configData.get('auth', 'permitted')
allowedDNs = filter(lambda x: x != '', config_dns.splitlines())


def _process_staging_request(transfer_id, product_id, callback):
    """Process a staging request."""
    log.msg("_process_staging_request (%s, %s)"
            % (product_id, callback))

    src_path = os.path.join(staging_src_dir, product_id)
    dst_path = os.path.join(staging_dst_dir, str(uuid.uuid1()))

    # Do the copy
    stagingError = None
    log.msg("About to link %s to %s" % (src_path, dst_path))
    try:
        os.mkdir(dst_path)
        dst_file = os.path.join(dst_path, str(product_id))
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_file)
        elif os.path.isfile(src_path):
            os.link(src_path, dst_file)
        else:
            raise Exception("Product %s not found" % product_id)
    except Exception, e:
        stagingError = e

    # Function to report results
    def _handle_reporting_error(failure, product_id, callback):
        failure.trap(Exception)
        log.err("Error reporting staging results for product %s to %s"
                % (product_id, callback))
        log.err(str(failure))

    if stagingError is not None:
        # Report error
        msg = ('Error copying product ID %s from %s to %s' %
               (product_id, src_path, dst_path))
        log.err(msg)
        log.err(str(e))
        success = False
    else:
        msg = 'Product %s staged successfully to %s' % (product_id, dst_path)
        success = True
    result = threads.deferToThread(requests.post,
                                   callback,
                                   data={'transfer_id': transfer_id,
                                         'product_id': product_id,
                                         'success': success,
                                         'staged_to': hostname(),
                                         'path': dst_path,
                                         'msg': msg},
                                   cert=(stager_cert, stager_key))
    result.addCallback(lambda r: log.msg("Staging of product %s "
                                         "reported (result: %s)"
                                         % (product_id, r.status_code)))
    result.addErrback(lambda e: _handle_reporting_error(e, product_id,
                                                        callback))


@app.route('/')
def root(request):
    """Called when a staging request has been received.

    Required params:
    transfer_id -- (Transfer service) identifier for the transfer being staged
    product_id -- Product ID to be staged
    callback -- URI of a transfer service URL to be called upon completion
        of the staging tasks
    """
    request.setHeader('Content-Type', 'application/json')

    # Extract certificate DN & verify authorization
    cert = request.transport.getPeerCertificate()
    basename = cert.get_subject()
    for i in range(0, cert.get_extension_count()):
        ext = cert.get_extension(i)
        if ext.get_short_name() == 'proxyCertInfo':
            basename = cert.get_issuer()
            break
    components = basename.get_components()
    components = map(lambda (x, y): '%s=%s' % (x, y), components)
    baseDN = '/' + '/'.join(components)
    if baseDN not in allowedDNs:
        request.setResponseCode(403)
        return json.dumps({'status': 'Unauthorized'})

    # Verify parameters
    try:
        transfer_id = request.args.get('transfer_id')[0]
        product_id = request.args.get('product_id')[0]
        callback = request.args.get('callback')[0]
    except Exception, e:
        # log.err(str(e))
        request.setResponseCode(400)
        return json.dumps({'status': 'Invalid parameters. A transfer_id, '
                           'product_id, and callback must be specified'})

    # Process request in separate thread
    reactor.callInThread(_process_staging_request, transfer_id, product_id,
                         callback)
    return json.dumps({'status': 'Request for product ID %s queued'
                      % product_id})


# Setup SSL
def _load_cert_function(x):
    return crypto.load_certificate(crypto.FILETYPE_PEM, x)
ctx_opt = {}
with open(ssl_cert, 'r') as f:
    ctx_opt['certificate'] = _load_cert_function(f.read())
with open(ssl_key, 'r') as f:
    ctx_opt['privateKey'] = crypto.load_privatekey(crypto.FILETYPE_PEM,
                                                   f.read())
with open(ssl_chain, 'r') as f:
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
ctx_opt['trustRoot'] = ssl.OpenSSLDefaultPaths()
ssl_ctx_factory = ssl.CertificateOptions(**ctx_opt)
# X509StoreFlags.ALLOW_PROXY_CERTS is what needs to be enabled for proxy certs
ssl_context = ssl_ctx_factory.getContext()
ssl_cert_store = ssl_context.get_cert_store()
ssl_cert_store.set_flags(crypto.X509StoreFlags.ALLOW_PROXY_CERTS)

endpoint = endpoints.SSL4ServerEndpoint(reactor, server_port, ssl_ctx_factory)
endpoint.listen(Site(app.resource()))
reactor.run()
