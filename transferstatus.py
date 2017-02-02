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

from __future__ import print_function # for python 2

__author__ = "David Aikema, <david.aikema@uct.ac.za>"

import json

from datetime import datetime
from twisted.logger import Logger
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

# API function fall: getStatus
# (allow users to query the results of their transfer request)
class TransferStatus (Resource):
  isLeaf = True
  def __init__(self, dbpool):
    Resource.__init__(self)
    self.dbpool = dbpool
    self.log = Logger()
  def render_GET(self, request):
    if 'job_id' not in request.args:
      result = {
        'error': True,
        'msg': 'No job ID specified'
      }
      request.setResponseCode(400)
      return json.dumps(result)

    def report_results(txn):
      job_id = request.args['job_id'][0]
      txn.execute("SELECT job_id, product_id, status, detailed_status, "
                  "destination_path, submitter, fts_jobid, fts_details, "
                  "stager_path, stager_hostname, stager_status, time_submitted, "
                  "time_staging, time_staging_finished, time_transferring, "
                  "time_error, time_success FROM "
                  "jobs WHERE job_id = %s", [job_id])
      result = txn.fetchone()
      if result:
        fields = ['job_id', 'product_id', 'status', 'detailed_status',
                  'destination_path', 'submitter', 'fts_jobid', 'fts_details',
                  'stager_path', 'stager_hostname', 'stager_status', 'time_submitted',
                  'time_staging', 'time_staging_finished', 'time_transferring',
                  'time_error', 'time_success']
        results = dict(zip(fields, result))
        def serialize_with_datetime (obj):
          if isinstance(obj,datetime):
            return obj.isoformat()
          raise TypeError ("Type not serializable")
        request.write(json.dumps(results, default=serialize_with_datetime) + "\n")
        #self.log.debug(str(result))
        #request.write("should report status of request for job {0}".format(
        #              request.args['job_id'][0]))
      else:
        request.setResponseCode(404)
        result = { 'msg': "job_id {0} not found".format(job_id) }
        request.write(json.dumps(result) + "\n")
      request.finish()

    d = self.dbpool.runInteraction(report_results)
    def report_db_error(e):
      self.log.error(e)
      result = {
        'error': True,
        'msg': 'An unknown database error occurred'
      }
      request.setResponseCode(500)
      request.write(json.dumps(result) + "\n")
      request.finish()
    d.addErrback(report_db_error)

    return NOT_DONE_YET
