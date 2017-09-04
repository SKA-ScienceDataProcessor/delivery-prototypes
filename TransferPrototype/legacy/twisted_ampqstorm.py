#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2016  University of Cape Town
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

import ConfigParser
import getpass
import json
import oauth2
import os
import random
import string
import sys
import threading
import time
import treq

import amqpstorm
from amqpstorm import Connection

from globus_sdk import AccessTokenAuthorizer, BasicAuthorizer, TransferClient, TransferData
from klein import run, route
from twisted.internet import defer, reactor
from twisted.internet.task import LoopingCall
from twisted.web.resource import Resource
from twisted.web._responses import BAD_REQUEST, INTERNAL_SERVER_ERROR, NOT_FOUND, NOT_IMPLEMENTED, UNAUTHORIZED

@route ('/')
def root(request):
  return "DELIV Prototype REST interface\n"

@route ('/transferRequest', methods=['POST'])
def queueTransferRequest(request):
  global staging_queue_name
  try:
    product_id = request.args.get('product_id')[0]
  except Exception, e:
    request.setResponseCode(BAD_REQUEST)
    ret = {'status': 'Error: product_id not specified'}
    return json.dumps(ret) 

  # Send a message to the queue
  msg = { 'product_id': product_id }
  send_message(staging_queue_name, json.dumps(msg))
  
  ret = {'status': "Transfer request queued for product {0}\n".format(product_id)}
  return json.dumps(ret)

def genAuthToken():
  token_len = int(configData.get('main', 'authtokenlen'))
  return ''.join(random.choice(string.lowercase) for i in range(token_len))

# @defer.inlineCallbacks
@route ('/doneStaging')
def doneStaging(request):
  global staging_lock
  global staging_in_progress
  global transfer_queue_name

  # Check params
  product_ids = request.args.get('product_id')
  if product_ids is None:
    request.setResponseCode(BAD_REQUEST)
    ret = {'status': 'Error: product_id not specified'}
    return json.dumps(ret)
  product_id = product_ids[0]
  try:
    authcode = request.args.get('authcode')[0]
  except Exception:
    request.setResponseCode(BAD_REQUEST)
    ret = {'status': 'Error: authcode not specified'}
    return json.dumps(ret)
  try:
    staged_file_path = request.args.get('path')[0]
  except Exception:
    request.setResponseCode(BAD_REQUEST)
    ret = {'status': 'Error: path to staged file not specified'}
    return json.dumps(ret)

  staging_lock.acquire()
  # Ensure product_id exists
  if product_id not in staging_in_progress:
    request.setResponseCode(NOT_FOUND)
    staging_lock.release()
    ret = {'status': 'Error: product_id not specified'}
    return json.dumps(ret)

  # Check authorization to edit job
  if staging_in_progress[product_id]['authkey'] != authcode:
    request.setResponseCode(UNAUTHORIZED)
    staging_lock.release()
    ret = {'status': 'Error: Invalid authorization code'}
    return json.dumps(ret)

  # Prepare message to transfer queue
  del staging_in_progress[product_id]
  params = { 'product_id': product_id, 'path': staged_file_path }
  send_message(transfer_queue_name, json.dumps(params))

  ret = { 'status': 'Product %s queued for transfer' % product_id }
  staging_lock.release()
  return json.dumps(ret)

@defer.inlineCallbacks
def send_message(queue, msg):
  reactor.callFromThread(print, "Publishing to %s '%s'" % (queue, msg))
  with connection.channel() as channel:
    yield channel.queue.declare(queue=queue)
    yield channel.basic.publish(exchange='',
                                routing_key=queue,
                                body=msg)

#@defer.inlineCallbacks
def get_message(queue):
  try:
    with connection.channel() as channel:
      channel.queue.declare(queue=queue)
      m = channel.basic.get(queue,auto_decode=False)
      if m is not None:
        m.ack()
      return m
  except Exception, e:
    reactor.callFromThread(print, "Exception retrieving message: %s" % e)
    reactor.stop()

@defer.inlineCallbacks
def transferManager ():
  global staging_lock
  global staging_queue_name
  global staging_in_progress
  global staging_max
  global staging_url
  global staging_username
  global staging_password
  global staging_callback_url

  global transfer_lock
  global transfer_queue_name
  global transfer_in_progress
  global transfer_max

  reactor.callFromThread(print, "calling transfer manager")

  # Check staging requests in progress ... if below the limit then check for new requests
  staging_lock.acquire()
  while len(staging_in_progress) < staging_max:
    m = get_message(staging_queue_name)
    if m is None:
      break
    job = json.loads(m.body)
    if job['product_id'] not in staging_in_progress.keys():
      job['authkey'] = genAuthToken()
      staging_in_progress[job['product_id']] = job
      yield treq.get(staging_url,
                     params={ 'product_id': job['product_id'],
                              'authcode': job['authkey'],
                              'callback': staging_callback_url },
                     auth=(staging_username, staging_password))
  staging_lock.release()

  # Check transfers in progress ... if below the limit then check for jobs done staging
  ensure_endpoints_active()
  transfer_lock.acquire()
  # prune any finished transfer
  for t in transfer_in_progress.keys():
    # Check status
    if transfer_is_done(transfer_in_progress[t]['task_id']):
      reactor.callFromThread(print,
                             "Finished transfer of %s, removing %s" % (
                             transfer_in_progress[t]['product_id'],
                             transfer_in_progress[t]['path']))
      os.remove(transfer_in_progress[t]['path'])
      del transfer_in_progress[t]
  # if transfers less than limit queue more
  #reactor.callFromThread(print, transfer_in_progress)
  while len(transfer_in_progress) < transfer_max:
    m = get_message(transfer_queue_name)
    if m is None:
      break
    job = json.loads(m.body)
    reactor.callFromThread(print, "Received %s" % m.body)
    transfer_in_progress[job['product_id']] = do_transfer(job)
  transfer_lock.release()

def do_transfer (job):
  global globus_src_ep
  global globus_dst_ep
  global globus_client
  filename = job['path']
  tdata = TransferData(globus_client,
                       globus_src_ep,
                       globus_dst_ep,
                       verify_checksum=True)
  tdata.add_item(filename, os.path.basename(filename))
  tr = globus_client.submit_transfer(tdata)
  job['task_id'] = tr.data['task_id']
  return job

def transfer_is_done (task_id):
  global globus_client
  task = globus_client.get_task(task_id)
  result = globus_client.get_task(task_id)
  return (result['status'] == 'SUCCEEDED')

def ensure_endpoints_active ():
  global globus_src_ep
  global globus_dst_ep
  global globus_client
  global myproxy_username
  global myproxy_password
  
  for ep_id in [globus_src_ep, globus_dst_ep]:
    r = globus_client.endpoint_autoactivate(ep_id, if_expires_in=3600)
    if r["code"] == "AutoActivationFailed":
      ar = r.data
      ar['DATA_TYPE'] = 'activation_requirements'
      for i in range(len(ar['DATA'])):
        if ar['DATA'][i]['name'] == 'username':
          ar['DATA'][i]['value'] = myproxy_username
        elif ar['DATA'][i]['name'] == 'passphrase':
          ar['DATA'][i]['value'] = myproxy_password
      globus_client.endpoint_activate(ep_id, ar)

# Load settings
path="~/.transfer.cfg"
configData = ConfigParser.ConfigParser()
configData.read(os.path.expanduser(path))

# Setup twisted connection
rabbit_host = configData.get('rabbitmq', 'hostname')
rabbit_user = configData.get('rabbitmq', 'username')
rabbit_pw = configData.get('rabbitmq', 'password')
connection = Connection(rabbit_host, rabbit_user, rabbit_pw)

# Setup staging / transfer vars
staging_lock = defer.DeferredLock()
staging_queue_name = configData.get('staging', 'queue_name')
staging_in_progress = {}
staging_max = int(configData.get('staging', 'max'))
staging_url = configData.get('staging', 'stager_url')
staging_username = configData.get('staging', 'stager_username')
staging_password = configData.get('staging', 'stager_password')
staging_callback_url = configData.get('staging', 'callback_url')
transfer_lock = defer.DeferredLock()
transfer_queue_name = configData.get('transfer', 'queue_name')
transfer_in_progress = {}
transfer_max = int(configData.get('transfer', 'max'))

# Prep for globus use
globus_client_id = configData.get('globus', 'client_id')
globus_client_secret = configData.get('globus', 'client_secret')

globus_src_ep = configData.get('source', 'endpoint')
globus_dst_ep = configData.get('destination', 'endpoint')

globus_client = TransferClient()

if 'MYPROXY_USERNAME' in os.environ:
  myproxy_username = os.environ['MYPROXY_USERNAME']
else:
   myproxy_username = raw_input('Enter username for myproxy: ')
if 'MYPROXY_PASSWORD' in os.environ:
  myproxy_password = os.environ['MYPROXY_PASSWORD']
else:
  myproxy_password = getpass.getpass('Enter password for myproxy: ')

#ensure_endpoints_active()

#sys.exit()

# if 'GLOBUS_USERNAME' in os.environ:
#   pass
# else:
#   pass
# if 'GLOBUS_PASSWORD' in os.environ:
#   pass
# else:
#   pass
# if 'MYPROXY_USERNAME' in os.environ:
#   pass
# else:
#   pass
# if 'MYPROXY_PASSWORD' in os.environ:
#   pass
# else:
#   pass
# if 'MYPROXY_SERVER' in os.environ:
#   pass
# else:
#   pass
#consumer = oauth2.Consumer(key=globus_client_id, secret=globus_client_secret)
#client = oauth2.Client(consumer)
#request_token_url = 'https://auth.globus.org/v2/oauth2/authorize'
#resp, content = client.request(request_token_url, "POST")

# Setup scheduler
interval = float(configData.get('main', 'interval'))
t_mgr = LoopingCall(transferManager)
t_mgr.start(interval)

# Use klein's run method to launch twisted
run('0.0.0.0', 8080)
