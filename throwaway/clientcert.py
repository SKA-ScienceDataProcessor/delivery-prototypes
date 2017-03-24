#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Root page for website."""
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

import ConfigParser
import sys
import twisted

from service_identity import CertificateError, VerificationError
from service_identity._common import DNS_ID, verify_service_identity
from service_identity.pyopenssl import extract_ids
from twisted.internet.interfaces import ISSLTransport

from OpenSSL import crypto, SSL
from OpenSSL.crypto import X509StoreFlags
from twisted.internet._sslverify import CertBase
from twisted.internet import defer, endpoints, protocol, reactor, ssl
from twisted.internet.interfaces import ISSLTransport
from twisted.logger import FileLogObserver, formatEvent, \
                           globalLogPublisher, Logger
from twisted.web.resource import Resource
from twisted.web.server import Site
__author__ = "David Aikema, <david.aikema@uct.ac.za>"


class RootPage (Resource):
    """Basic root webpage template."""

    def render_GET(self, request):
        """For now just return a basic message."""
        # service_identity module now used
        #print ('self:\t%s\n' % dir(self))
        #print ('request:\t%s\n' % dir(request))
        #print ('request.transport:\t%s\n' % dir(request.transport))

        #print ('client: %s\n' % request.transport.getPeerCertificate().get_subject())
        #transport = getattr(
        #    getattr(request, 'channel', None), 'transport', None)
        clientCertificate = request.transport.getPeerCertificate()
        if clientCertificate is not None:
            print('ssl subject:\t%s\n' % clientCertificate.get_subject())
            print('ssl info:\t%s\n' % dir(clientCertificate))
            #print('ssl class:\t%s\n' % clientCertificate.__class__)
            #print('ssl get_extension_count:\t%s\n' % clientCertificate.get_extension_count())
            for i in range(0,clientCertificate.get_extension_count()):
                e = clientCertificate.get_extension(i)
                if e.get_short_name() == 'proxyCertInfo':
                    #print (str(e.get_critical()) + '\n')
                    #print (str(e.get_data()) + '\n')
                    #print ('should try %s as real name' % clientCertificate.get_issuer())
                    #print('dir issuer: %s\n' % dir(clientCertificate.get_issuer()))
                    cc = clientCertificate.get_issuer()
                    print('/' + '/'.join(map(lambda (x,y): '%s="%s"' % (x,y), cc.get_components())))
                #print('ssl get_extension(%s):\t%s\n' % (i , e))
                #print('ssl e(%s):\t%s\n' %(i, dir(e)))
                #print ('get_short_name(): %s\n' % e.get_short_name())
            #from service_identity.pyopenssl import extract_ids
            #print (str(extract_ids(clientCertificate)) + "\n")
                
            
        else:
            print('No client certificate')
        #if ISSLTransport(transport, None) is not None:
        #    clientCertificate = transport.getPeerCertificate()   
        #    print ('client: %s\n' % clientCertificate.get_subject())
        #print ('ssl trans:\t%s\n' % ISSLTransport(request.transport, None))
        return "Transfer Service Prototype\n"

#log = Logger()
#observer = FileLogObserver(sys.stdout, lambda x: formatEvent(x) + "\n")
#globalLogPublisher.addObserver(observer)
#log.info("Initialized logging")
twisted.python.log.startLogging(sys.stdout)

configData = ConfigParser.ConfigParser()
configData.read('../transfer.cfg')

root = RootPage()
root.putChild('', root)

factory = Site(root)


def _load_cert_function(x):
    return crypto.load_certificate(crypto.FILETYPE_PEM, x)
ssl_cert = configData.get('ssl', 'cert')
ssl_key = configData.get('ssl', 'key')
ssl_trust_chain = configData.get('ssl', 'chain')
ctx_opt = {}
with open(ssl_cert, 'r') as f:
    ctx_opt['certificate'] = _load_cert_function(f.read())
with open(ssl_key, 'r') as f:
    ctx_opt['privateKey'] = crypto.load_privatekey(crypto.FILETYPE_PEM,
                                                   f.read())
with open(ssl_trust_chain, 'r') as f:
    certchain = []
    for line in f:
        if '-----BEGIN CERTIFICATE-----' in line:
            certchain.append(line)
        else:
            certchain[-1] = certchain[-1] + line
certchain_objs = map(_load_cert_function, certchain)
ctx_opt['extraCertChain'] = certchain_objs
ctx_opt['enableSingleUseKeys'] = True
ctx_opt['enableSessions'] = True
ctx_opt['trustRoot'] = ssl.OpenSSLDefaultPaths()
#ctx_opt['verify'] = True
#ctx_opt['requireCertificate'] = True
#ctx_opt['caCerts'] = ssl.OpenSSLDefaultPaths()

## Load GridCanada CA for client cert
#clientca_path = configData.get('ssl', 'clientca')
#with open(clientca_path, 'r') as f:
#    clientca_obj = _load_cert_function(f.read())
#    ctx_opt['trustRoot'] = ssl.trustRootFromCertificates([CertBase(clientca_obj)])

ssl_ctx_factory = ssl.CertificateOptions(**ctx_opt)

# Looks like cert verification can't be done without accessing private
# data in the CertificateOptions class
ssl_context = ssl_ctx_factory.getContext()  # create / get underlying OpenSSL context
ssl_cert_store = ssl_context.get_cert_store()  # OpenSSL context has a certstore
ssl_cert_store.set_flags(X509StoreFlags.ALLOW_PROXY_CERTS) # that cert store can be 
    # updates in place
    
# X509StoreFlags.ALLOW_PROXY_CERTS is what needs to be enabled to get proxy certs working
# need to execute set_flags on some X509Store object.
# OpenSSL.SSL.Context has a method called get_cert_store which returns an X509Store
sslendpoint = endpoints.SSL4ServerEndpoint(reactor, 8443,
                                           ssl_ctx_factory)
sslendpoint.listen(factory)

reactor.run()
