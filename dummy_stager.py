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
import treq
import uuid

from klein import run, route
from socket import gethostname as hostname
from twisted.internet import defer, reactor
from twisted.logger import Logger

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


@defer.inlineCallbacks
def _process_staging_request(job_id, product_id, callback, authcode):
    """Process a staging request."""
    log.info("_process_staging_request (%s, %s, %s)"
             % (product_id, callback, authcode))

    src_path = os.path.join(staging_src_dir, product_id)
    dst_path = os.path.join(staging_dst_dir,
                            str(product_id) + "-" + str(uuid.uuid1()))

    # Do the copy
    stagingError = None
    log.info("About to link %s to %s" % (src_path, dst_path))
    try:
        yield os.link(src_path, dst_path)
    except Exception, e:
        stagingError = e

    # Function to report results
    def _handle_reporting_error(failure, product_id, callback):
        failure.trap(Exception)
        log.error("Error reporting staging results for product %s to %s"
                  % (product_id, callback))
        log.error(str(failure))

    if stagingError is not None:
        # Report error
        msg = ('Error copying product ID %s from %s to %s' %
               (product_id, src_path, dst_path))
        log.error(msg)
        log.error(str(e))
        success = False
    else:
        msg = 'Product %s staged successfully to %s' % (product_id, dst_path)
        success = True
    treq_result = treq.get(callback, params={'job_id': job_id,
                                             'product_id': product_id,
                                             'authcode': authcode,
                                             'success': success,
                                             'staged_to': hostname(),
                                             'path': dst_path,
                                             'msg': msg})
    treq_result.addCallback(lambda r: log.info("Staging of product %s "
                                               "reported (result: %s)"
                                               % (product_id, r.code)))
    treq_result.addErrback(lambda e: _handle_reporting_error(e, product_id,
                                                             callback))


@route('/')
def root(request):
    """Called when a staging request has been received.

    Required params:
    job_id -- (Transfer service) identifier for the job being staged
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
        job_id = request.args.get('job_id')[0]
        product_id = request.args.get('product_id')[0]
        callback = request.args.get('callback')[0]
        authcode = request.args.get('authcode')[0]
    except Exception, e:
        log.error(e)
        request.setResponseCode(BAD_REQUEST)
        return json.dumps({'status': 'Invalid parameters. A job_id, '
                           'product_id, callback, and an authcode (for the '
                           'callback to pass along) '
                           'must be specified'})

    # Process request in separate thread
    reactor.callInThread(_process_staging_request, job_id, product_id,
                         callback, authcode)
    return json.dumps({'status': 'Request for product ID %s queued'
                      % product_id})

# Little init script
staging_src_dir = os.path.expanduser('~/products')
staging_dst_dir = os.path.expanduser('~/staging')

log = Logger()

# curl http://localhost:8081 -X POST -u fdsfdslakjvnc:fvngrq45u8ugfdlka -d \
# product_id=001 -d authcode=123 -d callback=http://localhost:8080/doneStaging
run('127.0.0.1', 8081)
