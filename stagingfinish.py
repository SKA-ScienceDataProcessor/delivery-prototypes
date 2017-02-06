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

from __future__ import print_function  # for python 2

from staging import finish_staging
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, \
                                   returnValue
from twisted.logger import Logger
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


# API function fall: doneStaging
# (have the stager signal that a job has been staged to local disk)
class StagingFinish (Resource):
    isLeaf = True

    def __init__(self, dbpool):
        Resource.__init__(self)
        self.dbpool = dbpool
        self.log = Logger()

    def render_GET(self, request):
        try:
            params = {
              'job_id': request.args['job_id'][0],
              'product_id': request.args['product_id'][0],
              'authcode': request.args['authcode'][0],
              'stager_success': request.args['success'][0],
              'staged_to': request.args['staged_to'][0],
              'path': request.args['path'][0],
              'msg': request.args['msg'][0]
            }
        except Exception:
            self.log.error('Invalid arguments calling doneStaging')
            request.setResponseCode(400)
            return('Invalid arguments\n')

        def _handle_finish_staging_result(success):
            if success:
                request.setResponseCode(200)
            else:
                self.log.error('finish_staging reported an error\n')
                request.setResponseCode(500)
            request.write('Finished processing staging callback\n')
            request.finish()

        def _handle_finish_staging_error(failure):
            self.log.error(failure)
            request.setResponseCode(500)
            request.write('Exception thrown running finish_staging\n')
            request.finish()

        d = finish_staging(**params)
        d.addCallback(_handle_finish_staging_result)
        d.addErrback(_handle_finish_staging_error)

        return NOT_DONE_YET

    def render_POST(self, request):
        return self.render_GET(request)
