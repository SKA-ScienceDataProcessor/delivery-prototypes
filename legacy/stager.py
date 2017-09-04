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
import json
import os
import shutil
import string
import sys
import treq
import uuid

from klein import run, route
from twisted.internet import defer, reactor
from twisted.web._responses import BAD_REQUEST, INTERNAL_SERVER_ERROR, NOT_FOUND, NOT_IMPLEMENTED, UNAUTHORIZED

@defer.inlineCallbacks
def process_staging_request (product_id, callback, authcode):

  reactor.callFromThread(print, "process_staging_request (%s, %s, %s)" % (product_id, callback, authcode))

  src_path = os.path.join(staging_src_dir, product_id)
  dst_path = os.path.join(staging_dst_dir,
                          str(product_id) + "-" + str(uuid.uuid1()))
  # Do the copy
  stagingError = None
  reactor.callFromThread(print, "About to copy %s to %s" % (src_path, dst_path))
  try:
    yield shutil.copy2(src_path, dst_path)
  except Exception, e:
    stagingError = e

  # Function to report results
  def handle_reporting_error(failure, product_id, callback):
    failure.trap(Exception)
    reactor.callFromThread(print, "Error reporting staging results for product %s to %s" % (product_id, callback))
    reactor.callFromThread(print, failure)
    
  if stagingError is not None:
    # Report error
    reactor.callFromThread(print, "Error copying product ID %s from %s to %s" %
                           (product_id, src_path, dst_path))
    reactor.callFromThread(print, e)
    msg = ('Error copying product ID %s from %s to %s' %
                           (product_id, src_path, dst_path))
    success = False
  else:
    msg = 'Product %s staged successfully to %s' % (product_id, dst_path)
    success = True    
  treq_result = treq.get(callback, params={'product_id': product_id,
                                            'authcode': authcode,
                                            'success': success,
                                            'path': dst_path,
                                            'msg': msg})
  treq_result.addCallback(lambda r: "Staging of product %s reported (result: %s)" % (product_id, r.code))
  treq_result.addErrback(lambda e: handle_reporting_error(e, product_id, callback))

@route ('/')
def root(request):
  request.setHeader('Content-Type', 'application/json')

  # Verify authorization
  if request.getUser() != username or request.getPassword() != password:
    request.setResponseCode(UNAUTHORIZED)
    return json.dumps({'status': 'Invalid username and/or password'})

  

  # Verify parameters
  try:
    reactor.callFromThread(print, request.args)
    product_id = request.args.get('product_id')[0]
    callback = request.args.get('callback')[0]
    authcode = request.args.get('authcode')[0]
  except Exception, e:
    reactor.callFromThread(print, e)
    request.setResponseCode(BAD_REQUEST)
    return json.dumps({'status': 'Invalid parameters. A product ID (product_id), a callback URL to report the result of the request to (callback), and an authorization code to provide with the callback (authcode) must be specified'})

  # Process request in separate thread
  reactor.callInThread(process_staging_request, product_id, callback, authcode)
  return json.dumps({'status': 'Request for product ID %s queued' % product_id})

# Load settings
path="~/.stager.cfg"
configData = ConfigParser.ConfigParser()
configData.read(os.path.expanduser(path))

username = configData.get('auth', 'username')
password = configData.get('auth', 'password')

staging_src_dir = configData.get('path', 'source')
staging_dst_dir = configData.get('path', 'dest')

 # curl http://localhost:8081 -X POST -u fdsfdslakjvnc:fvngrq45u8ugfdlka -d product_id=001 -d authcode=123 -d callback=http://localhost:8080/doneStaging
run('0.0.0.0', 8081)
