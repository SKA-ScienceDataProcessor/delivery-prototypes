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

from twisted.logger import Logger
from twisted.web.resource import Resource

__author__ = "David Aikema, <david.aikema@uct.ac.za>"


# Setup a root website
class RootPage (Resource):
    def __init__(self):
        Resource.__init__(self)
        self.log = Logger()

    def render_GET(self, request):
        return "Transfer Service Prototype\n"
