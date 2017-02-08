#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Handle job submissions."""
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
import pika
import random
import string
import uuid

from pika import exceptions
from pika.adapters import twisted_connection
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.logger import Logger
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from urlparse import urlparse

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


class SubmitException (Exception):
    """Track submit errors with option message and job ID.

    This is mounted at /submitTransfer.
    """

    def __init__(self, msg=None, job_id=None):
        """Denote an error, potentially associated with a message or job ID."""
        self.msg = msg
        self.job_id = job_id

    def toJSON(self):
        """Return error report in JSON format."""
        result = {'error': True, 'job_id': self.job_id, 'msg': self.msg}
        return json.dumps(result) + "\n"


class TransferSubmit (Resource):
    """Manage job submission, updating DB and RabbitMQ.

    Mounted at /submitTransfer.
    """

    isLeaf = True

    def __init__(self, dbpool, staging_queue, conn):
        """Initialize transfer submission REST interface.

        Arguments:
        dbpool -- shared database connection pool
        staging_queue -- named of the RabbitMQ queue to submit transfers to
        conn -- shared connection to RabbitMQ
        """
        Resource.__init__(self)

        # Use global logger and database pool
        self.log = Logger()
        self.dbpool = dbpool

        # Setup local connection to rabbitmq
        self.staging_queue = staging_queue
        self.pika_conn = conn
        bp = pika.BasicProperties(content_type='text/plain', delivery_mode=1)
        self.pika_send_properties = bp

    def render_POST(self, request):
        """Manage POST request with job submission.

        The request must contain the following parameters:
        product_id --- Unique identifier of the product being requested
        destination_path --- A URI specifying a GridFTP server location
            to transfer the product to.
        """
        # Check fields and return an error if any are missing
        for formvar in ['product_id', 'destination_path']:
            if formvar not in request.args:
                request.setResponseCode(400)
                result = {
                  'msg': 'Form did not specify {0}'.format(formvar),
                  'job_id': None,
                  'error': True,
                }
                return json.dumps(result) + "\n"

        # Validate URL
        try:
            up = urlparse(request.args['destination_path'][0])
            if up.scheme != 'gsiftp' or up.netloc == '':
                raise SubmitException()
            destination_path = up.geturl()
        except Exception, e:
            if not isinstance(e, SubmitException):
                self.log.error(e)
            request.setResponseCode(400)
            result = {
              'msg': 'destination_path must be a URL specifying '
                     'a GridFTP server',
              'job_id': None,
              'error': True,
            }
            return json.dumps(result) + "\n"

        # Doesn't validate this yet but probably should eventually
        product_id = request.args['product_id'][0]

        job_uuid = str(uuid.uuid1())
        callback = ''.join(random.choice(string.lowercase) for i in range(32))

        def _add_initial(txn):
            """Create initial database record for job.

            Argument:
            txn --- database cursor

            Note that the status of the record will be set to ERROR until
            the job has been successfully added to the RabbitMQ transfer queue.
            """
            try:
                txn.execute("INSERT INTO jobs (job_id, product_id, status, "
                            "destination_path, stager_callback, "
                            "time_submitted) VALUES (%s, %s, 'ERROR', %s, "
                            "%s, now())",
                            [job_uuid, product_id, destination_path, callback])
            except Exception, e:
                self.log.error(e)
                request.setResponseCode(500)
                raise SubmitException('Error creating database record',
                                      job_uuid)

        # Add to rabbitmq
        @inlineCallbacks
        def _add_to_rabbitmq(_):
            """Add the job to RabbitMQ."""
            channel = yield self.pika_conn.channel()
            yield channel.queue_declare(queue=self.staging_queue,
                                        exclusive=False, durable=True)
            yield channel.basic_publish('', self.staging_queue, job_uuid,
                                        self.pika_send_properties)

        def _update_job_status(txn):
            """Update status of the job in the DB to SUBMITTED."""
            try:
                txn.execute("UPDATE jobs SET status = 'SUBMITTED' WHERE "
                            "job_id = %s", [job_uuid])
            except Exception, e:
                self.log.error(e)
                request.setResponseCode(500)
                msg = 'Error updating job status to STAGING'
                result = {
                  'msg': msg,
                  'job_id': job_uuid,
                  'error': True
                }
                return json.dumps(result) + "\n"

        # Report results
        def _report_job_creation(_):
            """Report that the job submission was accepted with no errors."""
            result = {
              'msg': 'Job submission processed successfully',
              'error': False,
              'job_id': job_uuid
            }
            request.setResponseCode(202)
            request.write(json.dumps(result) + "\n")
            request.finish()
            self.log.info("Job submission of %s processed successfully"
                          % job_uuid)

        def _handleCreationError(e):
            """Report that an error occured when processing the job."""
            request.setResponseCode(500)
            if isinstance(SubmitException, e.value):
                request.write(e.toJSON())
            else:
                self.log.error(e)
                result = {
                  'msg': 'Unknown error handling job submission',
                  'job_id': job_uuid,
                  'error': True
                }
                request.write(json.dumps(result) + "\n")
            request.finish()

        # Add callbacks to handle the job submission asynchronously
        d = self.dbpool.runInteraction(_add_initial)
        d.addCallback(_add_to_rabbitmq)
        d.addCallback(lambda _: self.dbpool.runInteraction(_update_job_status))
        d.addCallback(_report_job_creation)
        d.addErrback(_handleCreationError)
        return NOT_DONE_YET
