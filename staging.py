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
import pika
import random
import string
import sys
import treq
import twisted

from twisted.internet import defer, reactor
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, returnValue
from twisted.logger import Logger

@inlineCallbacks
def finish_staging(job_id, product_id, authcode, stager_success, staged_to, path, msg):
  global transfer_queue
  global conn
  global sem_staging

  # Report stager failure is something other than success was reported
  if not stager_success:
    log.error('The stager reported failure')

  # Verify authcode against value returned from DB
  try:
    r = yield dbpool.runQuery("SELECT stager_callback FROM jobs WHERE "
                              "job_id = %s", [job_id])
    if r[0][0] != authcode:
      raise Exception('Invalid authcode %s for job %s' % authcode, job_id)
  except Exception, e:
    yield log.error(str(e))
    yield sem_staging.release()
    returnValue(False)

  # Update database information
  try:
    r = yield dbpool.runQuery("UPDATE jobs SET "
                              "time_staging_finished = now(), "
                              "stager_path = %s, "
                              "stager_hostname = %s, "
                              "stager_status = %s "
                              "WHERE job_id = %s",
                              [path, staged_to, msg, job_id])
  except Exception, e:
    yield log.error('Error updating DB to report staging finished for job %s' % job_id)
    yield log.error(str(e))
    yield sem_staging.release()
    returnValue(False)

  # Add to transfer queue
  try:
    pika_send_properties = pika.BasicProperties(content_type='text/plain',
                                                delivery_mode=1)
    channel = yield conn.channel()
    yield channel.queue_declare(queue=transfer_queue, exclusive=False, durable=False)
    yield channel.basic_publish('', transfer_queue, job_id, pika_send_properties)
  except Exception, e:
    yield log.error('Error add job %s to rabbitmq transfer queue' % job_id)
    yield log.error(str(e))
    yield sem_staging.release()
    returnValue(False)

  # Allow next job into staging and report results
  yield sem_staging.release()
  yield log.info("Completed staging of %s" % job_id)
  returnValue(True)

@inlineCallbacks
def send_to_staging(job_id, token_len=32):
  global log
  global dbpool
  global sem_staging
  global stager_url
  global stager_callback

  # Get job details from DB and create authcode for callback
  try:
    r = yield dbpool.runQuery("SELECT product_id FROM jobs WHERE job_id = %s",
                              [job_id])
    product_id = r[0][0]
  except Exception, e:
    yield log.error('Error retrieving product ID for job ID %s' % job_id)
    yield log.error(e)
    try:
      dbpool.runQuery("UPDATE jobs SET status = 'ERROR', detailed_status = 'Error "
                      "retrieving product ID when preparing to stage job' WHERE "
                      "job_id = %s", [job_id])
    except Exception:
      # Just log this one as it might have been a broken DB that triggered
      # the original error.
      log.error('Error updating DB with staging error for job %s' % job_id)
    # Abort the staging request as staging is impossible without a product ID
    yield sem_staging.release()
    returnValue(None)
  authcode = ''.join(random.choice(string.lowercase) for i in range(token_len))
  
  # Update job status to staging and add callback code
  try:
    yield dbpool.runQuery("UPDATE jobs SET status = 'STAGING', time_staging = now(), "
                          "stager_callback = %s WHERE job_id = %s", (authcode, job_id))
  except Exception:
    yield log.error('Error updating job status / recording stager callback code '
                    'for job %s' % job_id)
    yield sem_staging.release()
    returnValue(None)
  
  # Contact the stager to initiate the transfer process
  params = {
    'job_id': job_id,
    'product_id': product_id,
    'authcode': authcode,
    'callback': stager_callback,
  }
  try:
    r = yield treq.get(stager_url, params=params)
    if int(r.code) >= 400:
      raise Exception('The stager reported an error - status was %s' % r.code)
  except Exception, e:
    log.error('Error contacting stager at %s to submit request to stage product ID %s'
              ' for job ID %s' % (stager_callback, product_id, job_id))
    log.error(e)
    yield dbpool.runQuery("UPDATE jobs SET status = 'ERROR', detailed_status = "
                          "'Error contacting stager' WHERE job_id = %s", [job_id])

  yield log.info('Finished submitting job %s to stager' % job_id)

@inlineCallbacks
def staging_queue_listener():
  global log
  global conn
  global staging_queue
  global sem_staging

  #yield log.info("About to bind to staging queue")

  channel = yield conn.channel()
  queue = yield channel.queue_declare(queue=staging_queue,
                                      exclusive=False,
                                      durable=False)
  yield channel.basic_qos(prefetch_count=1)

  # Enter loop
  queue_object, consumer_tag = yield channel.basic_consume(queue=staging_queue,
                                                           no_ack=False)
  while True:
    #yield log.debug("about to acquire semaphore")
    yield sem_staging.acquire()
    #yield log.debug("semaphore acquired")
    ch,method,properties,body = yield queue_object.get()
    if body:
      reactor.callInThread(send_to_staging, [body])
      yield ch.basic_ack(delivery_tag=method.delivery_tag)

@inlineCallbacks
def init_staging(l_conn, l_dbpool, l_staging_queue, max_concurrent, s_url,
                 s_callback, l_transfer_queue):
  global log
  global conn
  global dbpool
  global sem_staging
  global staging_queue
  global stager_url
  global stager_callback
  global transfer_queue
  
  log = Logger()
  twisted.python.log.startLogging(sys.stderr)

  yield log.info("Initializing staging - ({0} job concurrency limit)".format(max_concurrent))

  conn = l_conn
  dbpool = l_dbpool
  sem_staging = DeferredSemaphore(int(max_concurrent))
  staging_queue = l_staging_queue
  stager_url = s_url
  stager_callback = s_callback
  transfer_queue = l_transfer_queue

  reactor.callInThread(staging_queue_listener)
