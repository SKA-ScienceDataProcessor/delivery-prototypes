#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Root page for website."""
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

import os
import os.path
import json

from twisted.internet import reactor
from twisted.logger import Logger
from twisted.web.server import NOT_DONE_YET


log = Logger()
allowedDNs = None
"""List of X.509 DNs of certificates which are permitted access."""


def load_allowed_DNs(val):
    """Load into memory a list of X.509 distinguished names allowed access."""
    global allowedDNs
    allowedDNs = filter(lambda x: x != '', val.splitlines())


def match_against_allowed(dn):
    """Check if a particular X.509 distinguished name is allowed access."""
    global allowedDNs
    if isinstance(allowedDNs, list):
        return (dn in allowedDNs)
    else:
        return False


def check_auth(request=None, transfer=None, returnError=True, mustMatch=None):
    """Check if request is authorized to do transfer.

    Arguments:
    request -- The request being evaluated

    Return Value:
        NOT_DONE_YET -- if returnError was set to True and the request wasn't
            authenticated

        X.509 DN -- the distinguished name of the authenticated user if a
            user was authenticated

        False -- if a user was not authenticated
    """
    if request is None:
        raise Exception('Request not passed in')

    def _get_base_name(cert):
        """Return DN after stripping off proxy."""
        try:
            for i in range(0, cert.get_extension_count()):
                ext = cert.get_extension(i)
                if ext.get_short_name() == 'proxyCertInfo':
                    return cert.get_issuer()
            return cert.get_subject()
        except Exception, e:
            log.error(e)
            return None

    # Extract distinguished name from certificate
    try:
        possible_proxy = request.transport.getPeerCertificate()
        basename = _get_base_name(possible_proxy)
        if basename is not None:
            components = basename.get_components()
            components = map(lambda (x, y): '%s=%s' % (x, y), components)
            baseDN = '/' + '/'.join(components)
            # log.info('Got DN: %s\n' % baseDN)
            if mustMatch is not None:
                return baseDN == mustMatch
            else:
                return baseDN
    except Exception, e:
        log.error(e)
        if returnError:
            request.setResponseCode(500)
            request.write(json.dumps({'error': True,
                                      'msg': 'Internal server error',
                                      'transfer_id': transfer
                                      }))
            request.finish()
            return NOT_DONE_YET
        raise Exception('error processing certificate')

    if returnError:
        request.setResponseCode(403)
        request.write(json.dumps({'error': True,
                                  'msg': 'Unauthorized',
                                  'transfer_id': transfer
                                  }))
        request.finish()
        return NOT_DONE_YET
    else:
        return False


def get_files_in_dir(path):
    """Return a list of files in the specified dir (and its subdirs).

    This is used to create a list of files which FTS is must transfer at a
    single point in time.

    Arguments:
        path -- The directory to traverse looking for files.

    Return Value:
        a list containing relative paths to file in the specified directory
        as well as in any subdirectories

    Warning:
        any exceptions encountered creating the list will *not* be captured
        by the function and should be handled upstream.
    """
    files = []
    realpath = os.path.realpath(path)
    for dir, _, filenames in os.walk(realpath):
        full = map(lambda x: os.path.join(dir, x), filenames)
        noprefix = map(lambda x: x[len(realpath) + len(os.sep):], full)
        files += noprefix
    return files
