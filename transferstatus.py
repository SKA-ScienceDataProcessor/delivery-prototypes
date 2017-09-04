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

from util import check_auth

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
        """Process GET request for transfer status.

        Required parameter:
        transfer_id -- identifier of the transfer to get status of.
        """
        if 'transfer_id' not in request.args:
            result = {
              'error': True,
              'msg': 'No transfer ID specified'
            }
            request.setResponseCode(400)
            return json.dumps(result)

        # Check auth
        x509dn = check_auth(request, request.args['transfer_id'][0],
                            returnError=False)

        def _report_results(txn):
            """Query DB for transfer and report results to user."""
            transfer_id = request.args['transfer_id'][0]
            txn.execute("SELECT transfer_id, product_id, status, "
                        "extra_status, destination_path, submitter, fts_id, "
                        "fts_details, stager_path, stager_hostname, "
                        "stager_status, prepare_activity, time_submitted, "
                        "time_staging, time_staging_done, time_transferring, "
                        "time_error, time_success FROM transfers WHERE "
                        "transfer_id = %s", [transfer_id])
            result = txn.fetchone()
            if result:
                fields = ['transfer_id', 'product_id', 'status',
                          'extra_status', 'destination_path', 'submitter',
                          'fts_id', 'fts_details', 'stager_path',
                          'stager_hostname', 'stager_status',
                          'prepare_activity', 'time_submitted',
                          'time_staging', 'time_staging_done',
                          'time_transferring', 'time_error', 'time_success']
                results = dict(zip(fields, result))

                # Check authZ
                if results['submitter'] != x509dn:
                    request.setResponseCode(403)
                    msg = "'%s' does not match submitter for transfer %s" % (
                           x509dn, request.args['transfer_id'][0])
                    request.write(json.dumps({'msg': msg}) + "\n")
                    request.finish()
                    return

                def _serialize_with_dt(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError("Type not serializable")
                request.write(json.dumps(results,
                                         default=_serialize_with_dt) + "\n")
            else:
                request.setResponseCode(404)
                result = {'msg': "transfer_id %s not found" % transfer_id}
                request.write(json.dumps(result) + "\n")
            request.finish()

        def _report_db_error(e):
            """Report error if issue encountered getting transfer status."""
            self.log.error(e)
            result = {
              'error': True,
              'msg': 'An unknown database error occurred'
            }
            request.setResponseCode(500)
            request.write(json.dumps(result) + "\n")
            request.finish()

        # Setup callbacks to return transfer status asynchronously
        d = self.dbpool.runInteraction(_report_results)
        d.addErrback(_report_db_error)
        return NOT_DONE_YET
