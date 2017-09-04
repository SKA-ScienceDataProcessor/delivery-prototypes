#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Manage interaction with FTS service."""
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

import fts3.rest.client.easy as fts3
import json
import os
import pika
import requests
import twisted

from os.path import basename
from time import sleep
from twisted.internet import reactor, threads
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, \
                                   returnValue
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


# FTS Updater
# (scans FTS server at a regular interval, updating the status of tasks)
@inlineCallbacks
def _FTSUpdater():
    """Contact FTS to update the status of transfers in TRANSFERRING state."""
    global _log
    global _dbpool
    global _fts_params
    global _sem_fts

    _log.info("Running FTS updater")

    # Initialize FTS context
    try:
        fts_context = fts3.Context(*_fts_params)
    except Exception, e:
        _log.error('Exception creating FTS context in _FTSUpdater')
        _log.error(str(e))
        returnValue(None)

    # Retrieve list of transfers currently submitted to FTS from DB
    try:
        r = yield _dbpool.runQuery("SELECT transfer_id, fts_id FROM transfers "
                                   "WHERE status='TRANSFERRING'")
    except Exception, e:
        _log.error('Error retrieving list of in transferring stage from DB')
        _log.error(str(e))
        returnValue(None)

    if r is None:
        _log.debug('FTS Updater found no transfers in the transferring state')
        returnValue(None)

    # for each transfer get FTS status
    transfersUpdated = 0
    for transfer in r:
        try:
            transfer_id = transfer[0]
            fts_id = transfer[1]
            fts_job_status = fts3.get_job_status(fts_context, fts_id,
                                                 list_files=True)

            # Compare and update
            state = fts_job_status['job_state']

            if state == 'FINISHED':
                _log.info('Transfer %s successfully completed using FTS'
                          % transfer_id)
                yield _dbpool.runQuery("UPDATE transfers SET status = "
                                       "'SUCCESS', fts_details = %s WHERE "
                                       "transfer_id = %s",
                                       [str(fts_job_status), transfer_id])
                yield _sem_fts.release()
                transfersUpdated += 1
            elif state == 'FAILED':
                _log.info('Transfer %s has failed during the transfer stage'
                          % transfer_id)
                yield _dbpool.runQuery("UPDATE transfers SET status = "
                                       "'ERROR', fts_details = %s WHERE "
                                       "transfer_id = %s",
                                       [str(fts_job_status), transfer_id])
                yield _sem_fts.release()
                transfersUpdated += 1
            else:
                yield _dbpool.runQuery("UPDATE transfers SET fts_details = %s "
                                       "WHERE transfer_id = %s",
                                       [str(fts_job_status), transfer_id])
                transfersUpdated += 1
        except Exception, e:
            _log.error('Error updating status for transfers in FTS manager')
            _log.error(str(e))
            returnValue(None)
    if transfersUpdated > 0:
        _log.debug('FTS Updater updated the status of %s transfers that were '
                   'in the TRANSFERRING state' % transfersUpdated)


@inlineCallbacks
def _start_fts_transfer(transfer_id):
    """Submit transfer request for transfer to FTS server and update DB."""
    global _log
    global _dbpool
    global _fts_params
    global _prepare_creds

    try:
        fts_context = fts3.Context(*_fts_params)
    except Exception, e:
        _log.error('Exception creating FTS context in _start_fts_transfer')
        _log.error(str(e))
        ds = "Failed to create FTS context when setting up transfer"
        _dbpool.runQuery("UPDATE transfers SET status='ERROR', "
                         "extra_status = %s WHERE transfer_id = %s",
                         [ds, transfer_id])
        returnValue(None)

    # Get information about the transfer from the database
    r = yield _dbpool.runQuery("SELECT stager_path, stager_hostname, "
                               "destination_path FROM transfers WHERE "
                               "transfer_id = %s",
                               [transfer_id])
    if r is None:
        _log.error('Invalid transfer_id %s received by FTS transfer service'
                   % transfer_id)
        returnValue(None)

    # Create the transfer request
    localpath = str(r[0][0])
    src = 'gsiftp://%s%s' % (r[0][1], str(r[0][0]).rstrip(os.sep))
    dst = '%s/%s' % (str(r[0][2]).rstrip('/'), basename(r[0][0]))
    _log.info("About to transfer '%s' to '%s' for transfer %s" %
              (src, dst, transfer_id))

    # Retrieve a list of file to add from the transfer agent running on the
    # transfer server
    transfer_host = 'https://%s:8444/files' % r[0][1]
    try:
        r = yield threads.deferToThread(requests.post, transfer_host,
                                        data={'dir': localpath},
                                        cert=(_prepare_creds))
        body = json.loads(r.text)
        if r.status_code != 200:
            raise Exception(body['msg'])

        files = body['files']
    except Exception, e:
        _log.error('Error retrieving file list for transfer %s from %s'
                    % (transfer_id, transfer_host))
        _log.error(str(e))
        _dbpool.runQuery("UPDATE transfers SET status='ERROR', extra_status = "
                         "%s WHERE transfer_id = %s", [str(e), transfer_id])

    # Setup the list of transfers and submit to FTS
    try:
        transfers = []
        for file in files:
            transfers.append(fts3.new_transfer(src + '/' + file,
                                               dst + '/' + file))

        fts_job = fts3.new_job(transfers)
        fts_id = fts3.submit(fts_context, fts_job)
        fts_job_status = fts3.get_job_status(fts_context, fts_id,
                                             list_files=True)
    except Exception, e:
        _log.error('Error submitting transfer %s to FTS' % transfer_id)
        _log.error(str(e))
        ds = "Error submitting transfer to FTS"
        _dbpool.runQuery("UPDATE transfers SET status='ERROR', extra_status = "
                         "%s WHERE transfer_id = %s", [ds, transfer_id])
        returnValue(None)

    # Update transfer status, add FTS ID & FTS status
    try:
        yield _dbpool.runQuery("UPDATE transfers SET status='TRANSFERRING', "
                               "fts_id = %s, "
                               "fts_details = %s WHERE transfer_id = %s",
                               [fts_id, str(fts_job_status), transfer_id])
    except Exception, e:
        _log.error('Error updating status for transfer %s' % transfer_id)
        _log.error(str(e))
        ds = "Error updating transfer status following FTS submission"
        _dbpool.runQuery("UPDATE transfers SET status='ERROR', extra_status "
                         "= %s WHERE transfer_id = %s", [ds, transfer_id])

        returnValue(None)
    _log.info('Transfer database updated; added FTS ID %s for transfer %s'
              % (fts_id, transfer_id))


@inlineCallbacks
def _transfer_queue_listener():
    """Wait for requests to come in via transfer queue.

    Note that only a bounded number of transfers are permitted
    to be in the transferring state at any point in time and this is enforced
    using a semaphore.
    """
    global _log
    global _transfer_queue
    global _pika_conn
    global _sem_fts

    channel = yield _pika_conn.channel()

    queue = yield channel.queue_declare(queue=_transfer_queue,
                                        exclusive=False,
                                        durable=True)
    yield channel.basic_qos(prefetch_count=1)

    # Enter loop
    queue, consumer_tag = yield channel.basic_consume(queue=_transfer_queue,
                                                      no_ack=False)

    while True:
        ch, method, properties, body = yield queue.get()
        if body:
            yield _sem_fts.acquire()
            reactor.callFromThread(_start_fts_transfer, body)
            yield ch.basic_ack(delivery_tag=method.delivery_tag)


def init_fts_manager(pika_conn, dbpool, fts_params, transfer_queue,
                     concurrent_max, polling_interval, prepare_creds):
    """Initialize services to manage transfers using FTS.

    This involves:
    * Initializing a thread to listen for requests to start
      transfers on the transfer queue
    * Scheduling a routine to run at a regular interval, querying the
      FTS server to update the status of transfers in the TRANSFERRING state.

    Note that this function also initializes a semaphore used to enforce a
    limit on the maximum number of transfer tasks which are permitted to take
    place in parallel.

    Parameters:
    pika_conn -- Global shared connection for RabbitMQ
    dbpool -- Global shared database connection pool
    fts_params -- A list of parameters to initialize the FTS service
        [URI of FTS server, path to certificate, path to key]
    transfer_queue -- Name of the RabbitMQ queue to which to listen for
      transfer requests
    concurrent_max -- Maximum number of transfers that are permitted to be
      in the TRANSFERRING stage at any point in time
    polling_interval -- Interval in seconds between polling attempts of
      the FTS server to update the status of transfers currently in the
      TRANSFERRING state
    prepare_creds -- A tuple containing filenames of a certificate and key
      used to authenticate with the transfer agent
    """
    global _log
    global _dbpool
    global _fts_params
    global _pika_conn
    global _prepare_creds
    global _transfer_queue
    global _sem_fts

    _log = Logger()

    _pika_conn = pika_conn
    _dbpool = dbpool
    _fts_params = fts_params
    _prepare_creds = prepare_creds
    _transfer_queue = transfer_queue
    _sem_fts = DeferredSemaphore(int(concurrent_max))

    # Start queue listener
    reactor.callFromThread(_transfer_queue_listener)

    # Run a task at a regular interval to update the status of
    # submitted transfers
    fts_updater_runner = LoopingCall(_FTSUpdater)
    fts_updater_runner.start(int(polling_interval))
