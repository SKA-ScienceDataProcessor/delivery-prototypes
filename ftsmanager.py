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

import fts3.rest.client.easy as fts3

from twisted.internet.task import LoopingCall
from twisted.logger import Logger

# FTS Updater
# (scans FTS server at a regular interval, updating the status of pending tasks)
def FTSUpdater():
  log = Logger()
  log.debug("Running FTS updater")

  # Retrieve list of jobs currently submitted to FTS from DB


  # Retrieve status of current jobs from FTS


  # Compare and update

def init_fts_manager(conn, dbpool, fts_server, fts_proxy, transfer_queue, fts_concurrent_max):
  pass