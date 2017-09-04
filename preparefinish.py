#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Web interface called when prepare tasks have been completed."""
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

from prepare import finish_prepare
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.logger import Logger
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

from util import check_auth

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


# API function fall: doneStaging
# (have the stager signal that a transfer has been staged to local disk)
class PrepareFinish (Resource):
    """Used to signal that a transfer has finished preprocessing.

    Mounted at /donePrepare.
    """

    isLeaf = True

    def __init__(self, prepare_dn):
        """Initialize preprocessing completion REST interface.

        Arguments:
        prepare_dn -- distinguished name of the X.509 cert connections
          should be accepting from.
        """
        Resource.__init__(self)
        self.prepare_dn = prepare_dn
        self.log = Logger()

    def render_GET(self, request):
        """Handle GET request reporting stager completion."""
        try:
            params = {
              'transfer_id': request.args['transfer_id'][0],
              'success': request.args['success'][0],
              'msg': request.args['msg'][0]
            }
        except Exception:
            self.log.error('Invalid arguments calling donePrepare')
            request.setResponseCode(400)
            return('Invalid arguments\n')

        def _handle_finish_prepare_result(success):
            """Report status of handling request to prepare system."""
            if success:
                request.setResponseCode(200)
            else:
                self.log.error('finish_prepare reported an error\n')
                request.setResponseCode(500)
            request.write('Finished processing prepare callback\n')
            request.finish()

        def _handle_finish_prepare_error(failure):
            """Report failure processing the prepare completion notice."""
            self.log.error(failure)
            request.setResponseCode(500)
            request.write('Exception thrown running finish_staging\n')
            request.finish()

        auth = check_auth(request, request.args['transfer_id'][0],
                          True, self.prepare_dn)
        if not auth:
            request.setResponseCode(403)
            request.write('Unauthorized')
            request.finish()

        # Setup deferred to manage finish_staging asynchronously
        d = finish_prepare(**params)
        d.addCallback(_handle_finish_prepare_result)
        d.addErrback(_handle_finish_prepare_error)
        return NOT_DONE_YET

    def render_POST(self, request):
        """If a POST request was received, process as if requested by GET."""
        return self.render_GET(request)
