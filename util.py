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

import json

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.web.server import NOT_DONE_YET


allowedDNs = None
"""List of X.509 DNs of certificates which are permitted access."""


def load_allowed_DNs(val):
    """Load into memory a list of X.509 distinguished names allowed access."""
    global allowedDNs
    allowedDNs = filter(lambda x: x != '', val.splitlines())


@inlineCallbacks
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

    def _get_base_certificate(cert):
        """Return DN of first non-proxy cert encountered."""
        try:
            for i in range(0, cert.get_extension_count()):
                ext = clientCertificate.get_extension(i)
                if ext.get_short_name() == 'proxyCertInfo':
                    return cert.get_issuer()
            return cert
        except Exception, e:
            return None

    # Extract distinguished name from certificate
    try:
        possible_proxy = request.transport.getPeerCertificate()
        basecert = _get_base_certificate(possible_proxy)
        if basecert is not None:
            components = basecert.get_components()
            components = map(lambda (x, y): '%s=%s' % (x, y), components)
            baseDN = '/' + '/'.join(components)
            print('Got DN: %s\n' % baseDN)
            if mustMatch is not None:
                returnValue(baseDN == mustMatch)
            else:
                returnValue(baseDN)
    except Exception, e:
        raise Exception('error processing certificate')

    if returnError:
        yield request.setResponseCode(403)
        yield request.write(json.dumps({'error': True,
                                        'msg': 'Unauthorized',
                                        'job_id': transfer
                                        }))
        yield request.finish()
        returnValue(NOT_DONE_YET)
    else:
        returnValue(False)
