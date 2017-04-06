#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Perform preprocessing on staged files before transfer."""
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

import pika
import json

from twisted.internet import reactor
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, \
                                   returnValue
from twisted.logger import Logger

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


@inlineCallbacks
def _do_prepare(transfer_id):
    """Perform preprocessing for the specified transfer ID.

    Params:
    transfer_id -- Identifier of the transfer to prepare
    """
    global _log
    global _dbpool
    global _sem_prepare
    global _pika_conn
    global _transfer_queue

    try:
        # Update the status of the job to note that prepare has started
        try:
            r = yield _dbpool.runQuery("UPDATE transfers SET status = "
                                       "'PREPARING' WHERE transfer_id = "
                                       "%s", [transfer_id])
        except Exception, e:
            yield _log.error('Error updating DB to report prepare started '
                             'for transfer %s' % transfer_id)
            yield _log.error(str(e))
            returnValue(False)

        # Retrieve information needed for prepare step to be run
        try:
            r = yield _dbpool.runQuery("SELECT prepare_activity, stager_path, "
                                       "stager_hostname FROM transfers WHERE "
                                       "transfer_id = %s", [transfer_id])
            prepare_activity = r[0][0]
            stager_path = r[0][1]
            stager_hostname = r[0][2]
        except Exception, e:
            yield _log.error('Error retrieving information from DB needed to '
                             'run prepare step for transfer %s' % transfer_id)
            yield _log.error(str(e))
            returnValue(False)

        # Do the prepare step itself
        if prepare_activity is not None:
            _log.info("SHOULD DO '%s' with TRANSFER '%s' in DIR '%s' on HOST "
                      "'%s'" % (prepare_activity, transfer_id, stager_path,
                                stager_hostname))
        else:
            _log.debug("No preprocessing to be done for transfer ID %s"
                       % transfer_id)

        # Then update the status of the job
        try:
            r = yield _dbpool.runQuery("UPDATE transfers SET status = "
                                       "'PREPARINGDONE' WHERE transfer_id = "
                                       "%s", [transfer_id])
        except Exception, e:
            yield _log.error('Error updating DB to report prepare finished '
                             'for transfer %s' % transfer_id)
            yield _log.error(str(e))
            returnValue(False)

        # And add to the transfer queue
        try:
            send_properties = pika.BasicProperties(content_type='text/plain',
                                                   delivery_mode=1)
            channel = yield _pika_conn.channel()
            yield channel.queue_declare(queue=_transfer_queue, exclusive=False,
                                        durable=True)
            yield channel.basic_publish('', _transfer_queue, transfer_id,
                                        send_properties)
        except Exception, e:
            yield _log.error('Error adding transfer %s to rabbitmq transfer '
                             'queue' % transfer_id)
            yield _log.error(str(e))
            returnValue(False)
        finally:
            yield channel.close()
        returnValue(True)
    finally:
        # Remember to release the semaphore once done
        yield _sem_prepare.release()


@inlineCallbacks
def _prepare_queue_listener():
    """Listen to the prepare queue and direct requests.

    Actual processing of these requests in done in a separate function
    called from here.  Note that a semaphore is used to ensure that only
    a fixed number of preprocessing tasks can be in process at any one time.
    """
    global _log
    global _pika_conn
    global _prepare_queue
    global _sem_prepare

    channel = yield _pika_conn.channel()
    queue = yield channel.queue_declare(queue=_prepare_queue,
                                        exclusive=False,
                                        durable=True)
    yield channel.basic_qos(prefetch_count=1)

    queue, _ = yield channel.basic_consume(queue=_prepare_queue,
                                           no_ack=False)

    while True:
        ch, method, properties, body = yield queue.get()
        if body:
            yield _sem_prepare.acquire()
            reactor.callFromThread(_do_prepare, body)
            yield ch.basic_ack(delivery_tag=method.delivery_tag)


def init_prepare(pika_conn, dbpool, prepare_queue, transfer_queue,
                 concurrent_max):
    """Init handling of preprocessing products before handling.

    Note that this function initializes a semaphore used to enforce a
    limit on the maximum number of preprocessing tasks permitted to take
    place in parallel.

    Parameters:
    pika_conn -- Global shared connection for RabbitMQ
    dbpool -- Global shared database connection pool
    prepare_queue -- Name of the RabbitMQ queue to which prepare requests
      should be sent.
    transfer_queue -- Name of the RabbitMQ queue to which to listen for
      transfer requests
    concurrent_max -- Maximum number of preprocessing tasks permitted to be
      in the PREPARING state at any point in time.
    """
    global _log
    global _dbpool
    global _pika_conn
    global _prepare_queue
    global _transfer_queue
    global _concurrent_max
    global _sem_prepare

    _log = Logger()

    _dbpool = dbpool
    _pika_conn = pika_conn
    _prepare_queue = prepare_queue
    _transfer_queue = transfer_queue
    _concurrent_max = concurrent_max
    _sem_prepare = DeferredSemaphore(int(concurrent_max))

    # Start queue listener
    reactor.callFromThread(_prepare_queue_listener)
