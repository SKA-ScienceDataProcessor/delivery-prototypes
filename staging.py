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

import treq
import json
import treq

from twisted.internet import defer, reactor
from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, returnValue
from twisted.logger import Logger

# Init global vars
log = None
conn = None
dbpool = None
sem_staging = None
staging_queue = None

# This file will contain code to listen to the staging queue and then
# interact with the staging software

def send_to_staging(sem, job_id):
  global log
  global dbpool
  global sem_staging

  log.info("Processing request to stage job {0}".format(job_id))

  log.debug("about to release semaphore")
  sem_staging.release()

@inlineCallbacks
def staging_queue_listener():
  global log
  global conn
  global staging_queue
  global sem_staging

  yield log.info("About to bind to staging queue")

  channel = yield conn.channel()
  queue = yield channel.queue_declare(queue=staging_queue,
                                      exclusive=False,
                                      durable=False)
  yield channel.basic_qos(prefetch_count=1)

  # Enter loop
  queue_object, consumer_tag = yield channel.basic_consume(queue=staging_queue,
                                                           no_ack=False)
  while True:
    log.debug("about to acquire semaphore")
#    yield sem_staging.acquire()
#    ch,method,properties,body = yield queue_object.get()
#    if body:
#      send_to_staging(body)
#    yield ch.basic_ack(delivery_tag=method.delivery_tag)

#@inlineCallbacks
def init_staging(l_conn, l_dbpool, l_staging_queue, max_concurrent):
  global log
  global conn
  global dbpool
  global sem_staging
  global staging_queue
  
  log = Logger()

  log.info("Initializing staging - ({0} job concurrency limit)".format(max_concurrent))

  conn = l_conn
  dbpool = l_dbpool
  sem_staging = DeferredSemaphore(int(max_concurrent))
  staging_queue = l_staging_queue

  log.info("Tokens:\t{0}".format(sem_staging.tokens))

  d = sem_staging.acquire()
  d.addCallback(lambda x: x.release())
  d.addCallback(lambda _: log.info("Acquired semaphore"))
  d.addErrback(lambda _: log.error("Received error"))
  #d = sem_staging.run(lambda _: log.info("run method"))

  #return d
  #log.info("Tokens:\t{0}".format(sem_staging.tokens))
  #reactor.callInThread(staging_queue_listener)
