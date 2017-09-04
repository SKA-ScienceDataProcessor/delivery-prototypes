#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A minimalist prepare agent.

This service performs X.509 authn/z of incoming requests but does not
allow for the status of current or past preprocessing tasks to be queried.
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
import requests
import sys

from klein import Klein
from OpenSSL import crypto
from os import walk
from os.path import dirname, exists, expanduser, isdir, join, relpath as \
                    relativepath, samefile
from twisted.internet import endpoints, reactor, ssl, threads
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log
from twisted.web.server import Site

__author__ = "David Aikema, <david.aikema@uct.ac.za>"

# Init Klein and logging
app = Klein()
log.startLogging(sys.stdout)

# Load config settings
cfg_file = expanduser('~/.transferagent.cfg')
if not exists(cfg_file):
    cfg_file = join(dirname(__file__), 'transferagent.cfg')
configData = ConfigParser.ConfigParser()
configData.read(cfg_file)

# Product locations
base_dir = configData.get('staged', 'basedir')

# Endpoint settings
ssl_cert = configData.get('ssl', 'cert')
ssl_key = configData.get('ssl', 'key')
ssl_chain = configData.get('ssl', 'chain')
server_port = int(configData.get('endpoint', 'port'))

# Get list of DNs allowed access
config_dns = configData.get('auth', 'permitted')
allowedDNs = filter(lambda x: x != '', config_dns.splitlines())

# Load credentials
creds = (configData.get('credentials', 'cert'),
         configData.get('credentials', 'key'))


def is_authorized(request, handle_unauthorized=True):
    """Assess if a request is authorized and optionally write error msg.

    Parameters:
    request -- the request to assess
    handle_unauthorized -- If true this request will write an error
      message in response to the request.

    Return Value:
    True/False -- whether or not authorized
    """
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
        if handle_unauthorized:
            request.setResponseCode(403)
            request.write(json.dumps({'success': False,
                                      'status': 'Unauthorized'}))
            request.finish()
        return False
    else:
        return True


def validate_product_directory(dir=None, request=None):
    """Check if the specified directory is valid. Optionally writes response.

    Params:
    dir -- Directory to validate.  (If None and a request is provided then
      the 'dir' param will be obtained from the request)
    request -- If provided the results will be written to this request

    Return values (if a request isn't specified):
    'OK'  -- If the directory is a subpath in in the staging area and exists
    'invalid' -- If the dir was outside the staging area
    'nonexistant' -- If the dir doesn't exist.

    Return values (if a request specified):
    True/False depending whether or not all checks satisfied.  If False,
    request will have been written.
    """
    # If a directory isn't provided look in the request for one
    if (dir is None and request is not None):
        if 'dir' not in request.args:
            request.setResponseCode(400)
            r = {'success': False,
                 'msg': '"dir" not specified'}
            request.write((json.dumps(r) + "\n"))
            request.finish()
            return False
        else:
            dir = request.args.get('dir')[0]

    # Report error unless the specified directory is contained within
    # the staged product folder
    relpath = relativepath(dir, base_dir)
    if os.pardir in relpath.split(os.sep) or samefile(base_dir, dir):
        if request is not None:
            request.setResponseCode(400)
            request.write(json.dumps({'success': False,
                                      'msg': 'Invalid directory'}) + "\n")
            request.finish()
            return None
        else:
            return 'invalid'

    # Report error if the product doesn't exist
    if not isdir(dir):
        if request is not None:
            request.setResponseCode(404)
            return (json.dumps({'success': False,
                                'msg': 'Staged product not found'}) + "\n")
        else:
            return 'nonexistant'

    # Passed all checks so return True
    return True


def validate_prepare_task(prepare, dir, transfer_id):
    """Validate whether or not the transfer request is well-formed.

    Params:
    prepare -- description of the prepare tasks
    dir -- base directory associated with the transfer
    transfer_id -- ID of the transfer

    Return Value:
    'Valid' if it passes, or an error string otherwise.
    """
    log.msg('PLACEHOLDER - validate_prepare_task called')
    return 'Valid'


def do_prepare(prepare, dir, transfer_id, callback):
    """Perform preprocessing task and report results to the callback.

    Params:
    prepare -- Description of the prepare task to be executed
    dir -- Directory containing the files
    transfer_id -- Transfer ID
    callback -- URL to report results of preprocessing to

    Note that this function is expected to be called in a separate
    thread and calls blocking operations.
    """
    log.msg('PLACEHOLDER -- do_prepare called')
    result_file = join(dir, 'preprocessed.txt')

    try:
        with open(result_file, 'w') as f:
            f.write(str(prepare) + "\n\n")
            f.write("Transfer ID:\t%s\n\n" % transfer_id)
            f.write("Could email Brad a reminder to send list of tasks\n")
    except Exception, e:
        log.err(e)
        # Report error to callback
        params = {'transfer_id': transfer_id,
                  'success': False,
                  'msg': str(e)}
        try:
            r = requests.post(callback, data=params, cert=creds)
            log.msg('Reported error in preprocessing %s to %s (result: %s)'
                    % (transfer_id, callback, r.status_code))
        except Exception, e:
            log.err('Error reporting preprocessing failure for %s to %s'
                    % (transfer_id, callback))
        return None

    # Report success to callback
    params = {'transfer_id': transfer_id,
              'success': True,
              'msg': 'Preprocessing task "%s" completed successfully'
                     % prepare}
    try:
        r = requests.post(callback, data=params, cert=creds)
        log.msg('Reported success preprocessing %s to %s (result: %s)'
                % (transfer_id, callback, r.status_code))
    except Exception, e:
        log.err('Error reporting preprocessing success for %s to %s'
                % (transfer_id, callback))


@app.route('/')
def root(request):
    """Root page for website.  No functionality offered."""
    return "Transfer Agent\n"


@app.route('/files')
def _files_page_handler(request):
    """Return a JSONified list of the files involved in a transfer.

    Request parameters:
    dir -- Base directory in which the product(s) are to be found.

    Explanation of return status codes:
    200 -- A valid list of files was found and is included with the reply
    400 -- Invalid data product directory.  This will be returned if the
           directory identified is not in the list of product base dirs (or
           no directory was specified)
    403 -- Authorization failed
    404 -- The data product was not found
    500 -- Server Error
    """
    def _get_list_of_files(path):
        # Build list of files
        files = []
        for dir, _, filenames in walk(path):
            full = map(lambda x: join(dir, x), filenames)
            noprefix = map(lambda x: x[len(path) + len(os.sep):], full)
            files += noprefix
        return files

    def _handle_list_of_files(files, request):
        r = {'success': True, 'files': files}
        request.write(json.dumps(r) + "\n")
        request.finish()

    def _handle_error(f, request):
        log.err(f)
        request.setResponseCode(500)
        request.write(json.dumps({'success': False,
                                  'msg': 'Internal server error'}) + "\n")
        request.finish()

    # Check authorization
    if not is_authorized(request):
        return None

    # Process the request
    if validate_product_directory(request=request):
        dir = request.args.get('dir')[0]

        # Launch function to handle request and return a deferred
        d = threads.deferToThread(_get_list_of_files, dir)
        d.addCallback(_handle_list_of_files, request)
        d.addErrback(_handle_error, request)
        return d


@app.route('/prepare')
def _prepare_page_handler(request):
    """Do preprocessing for the specified tasks.

    Request parameters:
    transfer_id -- identifier of the transfer
    dir -- Base directory in which the product(s) are to be found.
    prepare -- A description of the prepare task
    callback -- URL to callback to

    Explanation of return status codes:
    200 -- The prepare task was accepted for processing
    400 -- Invalid data product directory.  This will be returned if the
           directory identified is not in the list of product base dirs (or no
           directory was specified)
    403 -- Authorization failed
    404 -- The data product was not found
    422 -- Invalid preprocessing tasks specified.
    500 -- Server Error

    """
    # Check authorization
    if not is_authorized(request):
        return None

    # Validate directory param
    if not validate_product_directory(request=request):
        return None

    # Check other params
    for p in ['transfer_id', 'prepare', 'callback']:
        if p not in request.args:
            request.setResponseCode(400)
            r = {'success': False,
                 'msg': '"%s" not specified' % p}
            return (json.dumps(r) + "\n")

    prepare = request.args.get('prepare')[0]
    transfer_id = request.args.get('transfer_id')[0]
    dir = request.args.get('dir')[0]
    callback = request.args.get('callback')[0]

    # Validate prepare task
    r = validate_prepare_task(prepare, dir, transfer_id)
    if r != 'Valid':
        r = {'success': False,
             'msg': 'Error validating prepare for transfer %s' % transfer_id,
             'result': r}
        request.setResponseCode(422)
        request.write(json.dumps(r) + "\n")
        request.finish()
        return None

    reactor.callInThread(do_prepare, prepare, dir, transfer_id, callback)


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
ssl_context = ssl_ctx_factory.getContext()
ssl_cert_store = ssl_context.get_cert_store()
ssl_cert_store.set_flags(crypto.X509StoreFlags.ALLOW_PROXY_CERTS)

endpoint = endpoints.SSL4ServerEndpoint(reactor, server_port, ssl_ctx_factory)
endpoint.listen(Site(app.resource()))
reactor.run()
