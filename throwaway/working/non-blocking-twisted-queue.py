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

import pika

from pika import exceptions
from pika.adapters import twisted_connection
from twisted.internet import defer, reactor, protocol, task, threads
from twisted.internet.task import LoopingCall

@defer.inlineCallbacks
def do_consume(connection):
  print ("Launching do_consume")
  channel = yield connection.channel()
  queue = yield channel.queue_declare(queue='foo', exclusive=False, durable=False)
  yield channel.basic_qos(prefetch_count=1)
  
  #print ("Setup to consume from queue foo")
  #try:
  #  ch,method,properties,body = yield channel.basic_consume(queue='foo',no_ack=False)
  #  yield ch.basic_ack(delivery_tag=method.delivery_tag)
  #except Exception, e:
  #  print(e)

  queue_object, consumer_tag = yield channel.basic_consume(queue='foo',no_ack=False)
  while True:
    ch,method,properties,body = yield queue_object.get()
    if body:
      print ("CALLBACK: {0}".format(body))
    yield ch.basic_ack(delivery_tag=method.delivery_tag)

  print ("Finished consume of all objects")

  

print_foo = LoopingCall(print, 'foo')
print_foo.start(2.0)

parameters = pika.ConnectionParameters()
cc = protocol.ClientCreator(reactor, twisted_connection.TwistedProtocolConnection, parameters)
d = cc.connectTCP('localhost', 5672)
d.addCallback(lambda protocol: protocol.ready)
d.addCallback(do_consume)
d.addErrback(print)

print ("About to call reactor run")

reactor.run()