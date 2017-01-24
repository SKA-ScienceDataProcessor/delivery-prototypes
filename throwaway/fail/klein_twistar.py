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
from twistar.dbobject import DBObject
from twistar.registry import Registry
from twisted.enterprise import adbapi
from twisted.internet import defer, reactor
from twisted.web.server import NOT_DONE_YET

def Page(DBObject):
  pass

@route ('/')
#def root(request):
#  return "DELIV Prototype REST interface\n"
def loadroot(request):
  def getContents():
    return

# Setup an in-memory sqlite3 DB
#Registry.DBPOOL = adbapi.ConnectionPool('sqlite3', 'klein_twistar.db', check_same_thread=False)
Registry.DBPOOL = adbapi.ConnectionPool('MySQLdb', user="twistar", passwd="apass", db="test")
d = Registry.DBPOOL.runQuery("CREATE TABLE IF NOT EXISTS pages (location varchar(256), contents text)")
#d.addCallback(lambda: Registry.DBPOOL.runQuery("CREATE TABLE IF NOT EXISTS page (location BLOB, contents BLOB)"))

#d.addCallback(lambda: PageContents(location='/', contents='Twistar object for root page').save())

p = Page(location='/', contents='Twistar object for root page')
p.save()

#d.addCallback(lambda _: Registry.DBPOOL.runQuery("INSERT INTO page VALUES ('/', 'This is the default homepage')")

# Use klein's run method to launch twisted
run('0.0.0.0', 8080)

