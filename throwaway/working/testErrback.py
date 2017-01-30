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

from twisted.internet import reactor, threads
import time

class MyException(Exception):
  def print_stuff (self):
    print ("this is the exception handler")

def foo():
  #time.sleep(1)
  print("Hello from foo")
  return None

def bar(arg = None):
  raise(MyException())

def handler(e):
  print isinstance(e.value, MyException)
  e.value.print_stuff()
  reactor.stop()

d = threads.deferToThread(foo)
d.addCallback(bar)
d.addErrback(handler)
reactor.run()