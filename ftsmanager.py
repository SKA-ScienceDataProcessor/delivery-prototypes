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

import fts3.rest.client.easy as fts3
import json
import os
import pika
import twisted

from os.path import basename
from sys import stderr
from time import sleep
from twisted.internet import reactor
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


# FTS Updater
# (scans FTS server at a regular interval, updating the status of pending tasks)
@inlineCallbacks
def _FTSUpdater():
  global log
  global dbpool
  global server
  global sem_fts

  log.info("Running FTS updater")

  # Initialize FTS context
  try:
    fts_context = fts3.Context(server)
  except Exception, e:
    log.error('Exception creating FTS context in _FTSUpdater')
    log.error(str(e))
    returnValue(None)

  # Retrieve list of jobs currently submitted to FTS from DB
  try:
    r = yield dbpool.runQuery("SELECT job_id, fts_jobid FROM jobs WHERE "
                              "status='TRANSFERRING'")
  except Exception, e:
    log.error('Error retrieving list of in transferring stage from DB')
    log.error(str(e))
    returnValue(None)

  if r is None:
    log.info('FTS Updater found no jobs in the transferring state')
    returnValue(None)

  # for each job get FTS status
  try:
    for job in r:
      yield log.debug(job)
      job_id = job[0]
      fts_jobid = job[1]
      fts_job_status = fts3.get_job_status(fts_context, fts_jobid)

      # Compare and update
      state = fts_job_status['job_state']

      if state == 'FINISHED':
        log.info('Job %s successfully completed using FTS' % job_id)
        yield dbpool.runQuery("UPDATE jobs SET status = 'SUCCESS', "
                              "fts_details = %s WHERE job_id = %s",
                              [str(fts_job_status), job_id])
        yield sem_fts.release()
      elif state == 'FAILED':
        log.info('Job %s has failed during the transfer stage' % job_id)
        yield dbpool.runQuery("UPDATE jobs SET status = 'ERROR', "
                              "fts_details = %s WHERE job_id = %s",
                              [str(fts_job_status), job_id])
        yield sem_fts.release()
      else:
        yield dbpool.runQuery("UPDATE jobs SET fts_details = %s "
                              "WHERE job_id = %s",
                              [str(fts_job_status), job_id])
  except Exception, e:
    log.error('Error updating status for jobs in FTS manager')
    log.error(str(e))
    returnValue(None)
  log.info('FTS Updater finished updating jobs that were in transferring state')


@inlineCallbacks
def _start_fts_transfer(job_id):
  global log
  global dbpool
  global server

  try:
    fts_context = fts3.Context(server)
  except Exception, e:
    log.error('Exception creating FTS context in _start_fts_transfer')
    log.error(str(e))
    ds = "Failed to create FTS context when setting up transfer"
    dbpool.runQuery("UPDATE jobs SET status='ERROR', detailed_status = %s WHERE "
                    "job_id = %s", [ds, job_id])
    returnValue(None)

  # Get information about the transfer from the database
  r = yield dbpool.runQuery("SELECT stager_path, stager_hostname, destination_path "
                           "FROM jobs WHERE job_id = %s", [job_id])
  if r is None:
    log.error('Invalid job_id %s received by FTS transfer service' % job_id)
    returnValue(None)

  # Create the transfer request
  src = 'gsiftp://%s%s' % (r[0][1], str(r[0][0]).rstrip(os.sep))
  dst = '%s/%s' % (str(r[0][2]).rstrip('/'), basename(r[0][0]))
  log.info("About to transfer '%s' to '%s' for job %s" %
           (src, dst, job_id))
  try:
    transfer = fts3.new_transfer(src, dst)
    fts_job = fts3.new_job([transfer])
    fts_jobid = fts3.submit(fts_context, fts_job)
    fts_job_status = fts3.get_job_status(fts_context, fts_jobid)
  except Exception, e:
    log.error('Error submitting job %s to FTS' % job_id)
    log.error(str(e))
    ds = "Error submitting job to FTS"
    dbpool.runQuery("UPDATE jobs SET status='ERROR', detailed_status = %s WHERE "
                    "job_id = %s", [ds, job_id])
    returnValue(None)

  # Update job status, add FTS job ID & FTS status
  try:
    yield dbpool.runQuery("UPDATE jobs SET status='TRANSFERRING', fts_jobid = %s, "
                          "fts_details = %s WHERE job_id = %s",
                          [fts_jobid, str(fts_job_status), job_id])
  except Exception, e:
    log.error('Error updating status for job %s' % job_id)
    log.error(str(e))
    ds = "Error updating job status following FTS submission"
    dbpool.runQuery("UPDATE jobs SET status='ERROR', detailed_status = %s WHERE "
                    "job_id = %s", [ds, job_id])

    returnValue(None)
  log.info('Job database updated; add FTS ID %s for job %s' % (fts_jobid, job_id))


@inlineCallbacks
def _transfer_queue_listener():
  global log
  global transfer_queue
  global conn
  global sem_fts

  channel = yield conn.channel()
  queue = yield channel.queue_declare(queue=transfer_queue,
                                      exclusive=False,
                                      durable=False)
  yield channel.basic_qos(prefetch_count=1)

  # Enter loop
  queue_object, consumer_tag = yield channel.basic_consume(queue=transfer_queue,
                                                           no_ack=False)
  while True:
    yield sem_fts.acquire()
    ch, method, properties, body = yield queue_object.get()
    if body:
      reactor.callInThread(_start_fts_transfer, body)
      yield ch.basic_ack(delivery_tag=method.delivery_tag)

  pass


def init_fts_manager(l_conn, l_dbpool, fts_server, l_transfer_queue,
                     fts_concurrent_max, fts_polling_interval):
  global log
  global conn
  global dbpool
  global server
  global transfer_queue
  global sem_fts

  log = Logger()

  conn = l_conn
  dbpool = l_dbpool
  server = fts_server
  transfer_queue = l_transfer_queue
  sem_fts = DeferredSemaphore(int(fts_concurrent_max))

  # Start queue listener
  reactor.callInThread(_transfer_queue_listener)

  # Run a task at a regular interval to update the status of submitted jobs
  fts_updater_runner = LoopingCall(_FTSUpdater)
  fts_updater_runner.start(int(fts_polling_interval))
