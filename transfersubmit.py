#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Handle transfer submissions."""
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

from util import check_auth, match_against_allowed

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


class SubmitException (Exception):
    """Track submit errors with option message and transfer ID.

    This is mounted at /submitTransfer.
    """

    def __init__(self, msg=None, transfer_id=None):
        """Denote an error associated with a message or transfer ID."""
        self.msg = msg
        self.transfer_id = transfer_id

    def toJSON(self):
        """Return error report in JSON format."""
        result = {'error': True, 'transfer_id': self.transfer_id,
                  'msg': self.msg}
        return json.dumps(result) + "\n"


class TransferSubmit (Resource):
    """Manage transfer submission, updating DB and RabbitMQ.

    Mounted at /submitTransfer.
    """

    isLeaf = True

    def __init__(self, dbpool, staging_queue, pika_conn):
        """Initialize transfer submission REST interface.

        Arguments:
        dbpool -- shared database connection pool
        staging_queue -- named of the RabbitMQ queue to submit transfers to
        pika_conn -- shared connection to RabbitMQ
        """
        Resource.__init__(self)

        # Use global logger and database pool
        self._log = Logger()
        self._dbpool = dbpool

        # Setup local connection to rabbitmq
        self._staging_queue = staging_queue
        self._pika_conn = pika_conn
        self._pika_bp = pika.BasicProperties(content_type='text/plain',
                                             delivery_mode=1)

    def render_POST(self, request):
        """Manage POST request with transfer submission.

        The request must contain the following parameters:
        product_id --- Unique identifier of the product being requested
        destination_path --- A URI specifying a GridFTP server location
            to transfer the product to.
        """
        x509dn = check_auth(request, None, returnError=False)
        if x509dn == NOT_DONE_YET:
            return NOT_DONE_YET
        if not x509dn or not match_against_allowed(x509dn):
            request.setResponseCode(403)
            result = {
                  'msg': 'Unauthorized',
                  'transfer_id': None,
                  'error': True,
            }
            return json.dumps(result) + "\n"

        # Check fields and return an error if any are missing
        for formvar in ['product_id', 'destination_path']:
            if formvar not in request.args:
                request.setResponseCode(400)
                result = {
                  'msg': 'Form did not specify {0}'.format(formvar),
                  'transfer_id': None,
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
                self._log.error(e)
            request.setResponseCode(400)
            result = {
              'msg': 'destination_path must be a URL specifying '
                     'a GridFTP server',
              'transfer_id': None,
              'error': True,
            }
            return json.dumps(result) + "\n"

        # Doesn't validate this yet but probably should eventually
        product_id = request.args['product_id'][0]

        transfer_id = str(uuid.uuid1())

        def _add_initial(txn):
            """Create initial database record for transfer.

            Argument:
            txn --- database cursor

            Note that the status of the record will be set to INIT until
            the transfer has been successfully added to the RabbitMQ transfer
            queue.
            """
            try:
                txn.execute("INSERT INTO transfers (transfer_id, product_id, "
                            "status, destination_path, submitter) VALUES (%s, "
                            "%s, 'INIT', %s, %s)", [transfer_id, product_id,
                                                    destination_path, x509dn])
            except Exception, e:
                self._log.error(e)
                request.setResponseCode(500)
                raise SubmitException('Error creating database record',
                                      transfer_id)

        # Add to rabbitmq
        @inlineCallbacks
        def _add_to_rabbitmq(_):
            """Add the transfer to RabbitMQ."""
            channel = yield self._pika_conn.channel()
            yield channel.queue_declare(queue=self._staging_queue,
                                        exclusive=False, durable=True)
            yield channel.basic_publish('', self._staging_queue, transfer_id,
                                        self._pika_bp)

        def _update_status(txn):
            """Update status of the transfer in the DB to SUBMITTED."""
            try:
                txn.execute("UPDATE transfers SET status = 'SUBMITTED' WHERE "
                            "transfer_id = %s", [transfer_id])
            except Exception, e:
                self._log.error(e)
                request.setResponseCode(500)
                msg = 'Error updating transfer status to STAGING'
                result = {
                  'msg': msg,
                  'transfer_id': transfer_id,
                  'error': True
                }
                return json.dumps(result) + "\n"

        # Report results
        def _report_transfer_creation(_):
            """Report that transfer submission was accepted with no errors."""
            result = {
              'msg': 'Transfer submission processed successfully',
              'error': False,
              'transfer_id': transfer_id
            }
            request.setResponseCode(202)
            request.write(json.dumps(result) + "\n")
            request.finish()
            self._log.info("Transfer submission of %s processed successfully"
                           % transfer_id)

        def _handleCreationError(e):
            """Report that an error occured when processing the transfer."""
            request.setResponseCode(500)
            if isinstance(e, SubmitException):
                request.write(e.toJSON())
            else:
                self._log.error(e)
                result = {
                  'msg': 'Unknown error handling transfer submission',
                  'transfer_id': transfer_id,
                  'error': True
                }
                request.write(json.dumps(result) + "\n")
            request.finish()

        # Add callbacks to handle the transfer submission asynchronously
        d = self._dbpool.runInteraction(_add_initial)
        d.addCallback(_add_to_rabbitmq)
        d.addCallback(lambda _: self._dbpool.runInteraction(_update_status))
        d.addCallback(_report_transfer_creation)
        d.addErrback(_handleCreationError)
        return NOT_DONE_YET
