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
from klein import run, route
from twisted.enterprise import adbapi
from twisted.internet import defer #, reactor
#from twisted.web.server import NOT_DONE_YET

@route ('/')
#def root(request):
#  return "DELIV Prototype REST interface\n"
def loadroot(request):
  def getContents(txn):
    try:
      # With mysql python driver seem to need to use %s not ? like in the docs
      txn.execute("SELECT contents FROM pages WHERE location = %s", ['/'])
      result = txn.fetchone()
      request.write(result[0])
    except Exception, e:
      print (e)
      request.write('No page contents found')
    request.finish()
  
  location = "/"
  d = dbpool.runInteraction(getContents)
  
  # With klein it seems necessary to 
  return d

# Setup DB connection
dbpool = adbapi.ConnectionPool('MySQLdb', user="twistar", passwd="apass", db="test")

# Load some default values (can ignore warnings)
d = dbpool.runOperation("CREATE TABLE IF NOT EXISTS pages (location varchar(256), contents text, primary key(location))")
d.addCallback(lambda x: dbpool.runOperation("INSERT IGNORE INTO pages VALUES ('/', 'This is the default homepage')"))

# Use klein's run method to launch twisted
run('0.0.0.0', 8080)

