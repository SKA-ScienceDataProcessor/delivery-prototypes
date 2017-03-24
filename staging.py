#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Listen for staging requests to arrive, and make calls to stager."""
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
import requests
import twisted

from string import lowercase
from sys import stderr
from twisted.internet import defer, reactor, threads
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, \
                                   returnValue
from twisted.logger import Logger

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


@inlineCallbacks
def finish_staging(transfer_id, product_id, authcode, stager_success, staged_to,
                   path, msg):
    """Update status when a staging task has been completed.

    This is called by StagingFinish when it has received notification from
    the stager that a task has been completed.

    The function verifies the authcode recieved, updates the database to
    reflect the completion of the task, and updates the semaphore to allow
    another transfer to enter the STAGING portion of the transfer process.

    Required parameters:
    transfer_id -- ID of the transfer the product was staged as part of
    product_id -- ID of the product that was staged
    authcode -- Authcode used by the stager to verify its identity
    stager_success -- Whether or not the stager reported success
    staged_to -- Hostname of the system to which the product was staged
    path -- Path of the staged file on the system it was staged to.
    msg -- A message returned from the stager

    Return value:
    A boolean indicating whether or not an error was successfully processed.
    """
    global _dbpool
    global _transfer_queue
    global _pika_conn
    global _sem_staging

    # Report stager failure is something other than success was reported
    if not stager_success:
        _log.error('The stager reported failure staging transfer %s' % transfer_id)
        yield _sem_staging.release()
        returnValue(False)

    # Verify authcode against value returned from DB
    try:
        r = yield _dbpool.runQuery("SELECT stager_callback FROM transfers WHERE "
                                   "transfer_id = %s", [transfer_id])
        if r[0][0] != authcode:
            raise Exception('Invalid authcode %s for transfer %s' % authcode,
                            transfer_id)
    except Exception, e:
        yield _log.error(str(e))
        yield _sem_staging.release()
        returnValue(False)

    # Update database information
    try:
        r = yield _dbpool.runQuery("UPDATE transfers SET "
                                   "status = 'DONESTAGING', "
                                   "time_staging_finished = now(), "
                                   "stager_path = %s, "
                                   "stager_hostname = %s, "
                                   "stager_status = %s "
                                   "WHERE transfer_id = %s",
                                   [path, staged_to, msg, transfer_id])
    except Exception, e:
        yield _log.error('Error updating DB to report staging finished for '
                         'transfer %s' % transfer_id)
        yield _log.error(str(e))
        yield _sem_staging.release()
        returnValue(False)

    # Add to transfer queue
    try:
        pika_send_properties = pika.BasicProperties(content_type='text/plain',
                                                    delivery_mode=1)
        channel = yield _pika_conn.channel()
        yield channel.queue_declare(queue=_transfer_queue, exclusive=False,
                                    durable=True)
        yield channel.basic_publish('', _transfer_queue, transfer_id,
                                    pika_send_properties)
    except Exception, e:
        yield _log.error('Error adding transfer %s to rabbitmq transfer queue'
                         % transfer_id)
        yield _log.error(str(e))
        yield _sem_staging.release()
        returnValue(False)
    finally:
        yield channel.close()

    # Allow next transfer into staging and report results
    yield _log.info("Completed staging of %s" % transfer_id)
    yield _sem_staging.release()
    returnValue(True)


@inlineCallbacks
def _send_to_staging(transfer_id, token_len=32):
    """Make call to stager to process transfer and update DB accordingly.

    Params:
    transfer_id -- Identifier of the transfer to stage
    token_len -- Optional value specifying the length of the authcode
      token passed to the stager for it to verify its identity when
      reporting the completion of the staging process.
    """
    global _log
    global _dbpool
    global _sem_staging
    global _stager_uri
    global _stager_callback

    # Get transfer details from DB and create authcode for callback
    try:
        r = yield _dbpool.runQuery("SELECT product_id FROM transfers WHERE "
                                   "transfer_id = %s", [transfer_id])
        product_id = r[0][0]
    except Exception, e:
        yield _log.error('Error retrieving product ID for transfer ID %s' % transfer_id)
        yield _log.error(e)
        try:
            _dbpool.runQuery("UPDATE transfers SET status = 'ERROR', "
                             "extra_status = 'Error retrieving product ID "
                             "when preparing to stage transfer' WHERE "
                             "transfer_id = %s", [transfer_id])
        except Exception:
            # Just _log this one as it might have been a broken DB that
            # triggered the original error.
            _log.error('Error updating DB with staging error for transfer %s'
                       % transfer_id)
        # Abort the staging request as it's impossible without a product ID
        yield _sem_staging.release()
        returnValue(None)
    authcode = ''.join(random.choice(lowercase) for i in range(token_len))

    # Update transfer status to staging and add callback code
    try:
        yield _dbpool.runQuery("UPDATE transfers SET status = 'STAGING', "
                               "time_staging = now(), "
                               "stager_callback = %s WHERE transfer_id = %s",
                               (authcode, transfer_id))
    except Exception:
        yield _log.error('Error updating transfer status / recording stager '
                         'callback code for transfer %s' % transfer_id)
        yield _sem_staging.release()
        returnValue(None)

    # Contact the stager to initiate the transfer process
    params = {
      'transfer_id': transfer_id,
      'product_id': product_id,
      'authcode': authcode,
      'callback': _stager_callback,
    }
    try:
        r = yield threads.deferToThread(requests.post, _stager_uri, data=params)
        if int(r.status_code) >= 400:
            raise Exception('The stager reported an error - status was %s'
                            % r.code)
    except Exception, e:
        _log.error('Error contacting stager at %s to submit request to stage '
                   'product ID %s for transfer ID %s'
                   % (_stager_callback, product_id, transfer_id))
        _log.error(e)
        yield _dbpool.runQuery("UPDATE transfers SET status = 'ERROR', "
                               "extra_status = 'Error contacting stager' "
                               "WHERE transfer_id = %s", [transfer_id])

    yield _log.info('Finished submitting transfer %s to stager' % transfer_id)


@inlineCallbacks
def _staging_queue_listener():
    """Listen to the staging queue and handle requests.

    Actual processing of the incoming requests is done in a separate thread
    as setup here. Note that a semaphore is used to ensure that only a fixed
    number of transfers can be in staging process at one time.
    """
    global _log
    global _pika_conn
    global _staging_queue
    global _sem_staging

    channel = yield _pika_conn.channel()
    queue = yield channel.queue_declare(queue=_staging_queue,
                                        exclusive=False,
                                        durable=True)
    yield channel.basic_qos(prefetch_count=1)

    queue, _ = yield channel.basic_consume(queue=_staging_queue,
                                           no_ack=False)

    while True:
        ch, method, properties, body = yield queue.get()
        if body:
            yield _sem_staging.acquire()
            reactor.callFromThread(_send_to_staging, body)
            yield ch.basic_ack(delivery_tag=method.delivery_tag)


@inlineCallbacks
def init_staging(pika_conn, dbpool, staging_queue, max_concurrent, stager_uri,
                 stager_callback, transfer_queue):
    """Initialize thread to manage the staging process.

    Note that this function also initializes a semaphore used to enforce a
    limit on the maximum number of staging tasks which are permitted to be
    done in parallel.

    Parameters:
    pika_conn -- Globally shared RabbitMQ connection
    l_dbpool -- Globally shared database connection pool
    staging_queue -- Name of RabbitMQ queue to which staging requests are
      beging sent.
    max_concurrent -- Maximum number of transfers permitted to be in the STAGING
      state at any point in time
    stager_uri -- URI of the stager
    stager_callback -- Callback for stager to contact once staging complete
    transfer_queue -- Name of the RabbitMQ queue to which transfer requests
      should be sent.
    """
    global _dbpool
    global _log
    global _pika_conn
    global _sem_staging
    global _staging_queue
    global _stager_uri
    global _stager_callback
    global _transfer_queue

    _log = Logger()

    yield _log.info("Initializing staging (max %s concurrent)"
                    % max_concurrent)

    _pika_conn = pika_conn
    _dbpool = dbpool
    _sem_staging = DeferredSemaphore(int(max_concurrent))
    _staging_queue = staging_queue
    _stager_uri = stager_uri
    _stager_callback = stager_callback
    _transfer_queue = transfer_queue

    reactor.callFromThread(_staging_queue_listener)
