#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A minimalist staging engine simulator.

This service only binds to the loopback interface, performs no authorization
checks, and maintains no state information about staging tasks either in
process or completed.
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
import string
import sys
import requests
import uuid

from klein import Klein
from os.path import dirname, exists, expanduser, join, realpath
from socket import gethostname as hostname
from twisted.internet import endpoints, reactor, threads
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


@inlineCallbacks
def _process_staging_request(transfer_id, product_id, callback, authcode):
    """Process a staging request."""
    log.msg("_process_staging_request (%s, %s, %s)"
            % (product_id, callback, authcode))

    src_path = os.path.join(staging_src_dir, product_id)
    dst_path = os.path.join(staging_dst_dir,
                            str(product_id) + "-" + str(uuid.uuid1()))

    # Do the copy
    stagingError = None
    log.msg("About to link %s to %s" % (src_path, dst_path))
    try:
        yield os.link(src_path, dst_path)
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
                                         'authcode': authcode,
                                         'success': success,
                                         'staged_to': hostname(),
                                         'path': dst_path,
                                         'msg': msg})
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
    authcode -- Used to verify the identity of the stager when calling
        the callback URI.
    """
    request.setHeader('Content-Type', 'application/json')

    # Verify authorization
    # if request.getUser() != 'user' or request.getPassword() != 'pass':
    #   request.setResponseCode(403)
    #   return json.dumps({'status': 'Invalid username and/or password'})

    # Verify parameters
    try:
        transfer_id = request.args.get('transfer_id')[0]
        product_id = request.args.get('product_id')[0]
        callback = request.args.get('callback')[0]
        authcode = request.args.get('authcode')[0]
    except Exception, e:
        # log.err(str(e))
        request.setResponseCode(400)
        return json.dumps({'status': 'Invalid parameters. A transfer_id, '
                           'product_id, callback, and an authcode (for the '
                           'callback to pass along) '
                           'must be specified'})

    # Process request in separate thread
    reactor.callInThread(_process_staging_request, transfer_id, product_id,
                         callback, authcode)
    return json.dumps({'status': 'Request for product ID %s queued'
                      % product_id})


# Setup HTTP
endpoint = endpoints.TCP4ServerEndpoint(reactor, 8081,
                                        interface='127.0.0.1')
endpoint.listen(Site(app.resource()))
reactor.run()
