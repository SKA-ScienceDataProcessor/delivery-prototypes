#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Enable users to obtain status of transfers."""
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

from datetime import datetime
from twisted.logger import Logger
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


class TransferStatus (Resource):
    """Allow users to query the results of their transfer request.

    Mounted at /transferStatus.
    """

    isLeaf = True

    def __init__(self, dbpool):
        """Initialize transfer status query REST interface.

        Arguments:
        dbpool -- shared database connection pool
        """
        Resource.__init__(self)
        self.dbpool = dbpool
        self.log = Logger()

    def render_GET(self, request):
        """Process GET request for job status.

        Required parameter:
        job_id -- identifier of the job to get status of.
        """
        if 'job_id' not in request.args:
            result = {
              'error': True,
              'msg': 'No job ID specified'
            }
            request.setResponseCode(400)
            return json.dumps(result)

        def _report_results(txn):
            """Query DB for job and report results to user."""
            job_id = request.args['job_id'][0]
            txn.execute("SELECT job_id, product_id, status, detailed_status, "
                        "destination_path, submitter, fts_jobid, fts_details, "
                        "stager_path, stager_hostname, stager_status, "
                        "time_submitted, time_staging, time_staging_finished, "
                        "time_transferring, time_error, time_success FROM "
                        "jobs WHERE job_id = %s", [job_id])
            result = txn.fetchone()
            if result:
                fields = ['job_id', 'product_id', 'status', 'detailed_status',
                          'destination_path', 'submitter', 'fts_jobid',
                          'fts_details', 'stager_path', 'stager_hostname',
                          'stager_status', 'time_submitted', 'time_staging',
                          'time_staging_finished', 'time_transferring',
                          'time_error', 'time_success']
                results = dict(zip(fields, result))

                def _serialize_with_dt(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError("Type not serializable")
                request.write(json.dumps(results,
                                         default=_serialize_with_dt) + "\n")
            else:
                request.setResponseCode(404)
                result = {'msg': "job_id {0} not found".format(job_id)}
                request.write(json.dumps(result) + "\n")
            request.finish()

        def _report_db_error(e):
            """Report error if an issue was encountered getting job status."""
            self.log.error(e)
            result = {
              'error': True,
              'msg': 'An unknown database error occurred'
            }
            request.setResponseCode(500)
            request.write(json.dumps(result) + "\n")
            request.finish()

        # Setup callbacks to return job status asynchronously
        d = self.dbpool.runInteraction(_report_results)
        d.addErrback(_report_db_error)
        return NOT_DONE_YET
