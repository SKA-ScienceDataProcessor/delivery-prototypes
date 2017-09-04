Purpose
===

This service is responsible for performing tasks which must be run on the transfer
nodes.  The following tasks have been implemented:

* Performing preprocessing activities on staged data (`/prepare`)

* Creating a list of the files associated with a specific transfer (`/files`)

Additional operations are expected to be added to this transfer agent in the future.
These include:

* Reporting whether or not files associated with a transfer still remain on the node

* Removing files associated with a transfer

API
===

/prepare
---

Params:

* `transfer_id` -- identifier of the transfer

* `dir` -- Base directory in which the product(s) are to be found.

* `prepare` -- A description of the prepare task

* `callback` -- URL to callback to

Response codes:

* 200 -- The prepare task was accepted for processing

* 400 -- Invalid data product directory.  This will be returned if the
    directory identified is not in the list of product base dirs (or no
    directory was specified)
           
* 403 -- Authorization failed

* 404 -- The data product was not found

* 422 -- Invalid preprocessing tasks specified.

* 500 -- Server Error

/files
---

Params:

* `dir` -- Base directory in which the product(s) are to be found.

Response codes:

* 200 -- A valid list of files was found and is included with the reply

* 400 -- Invalid data product directory.  This will be returned if the
    directory identified is not in the list of product base dirs (or
    no directory was specified)

* 403 -- Authorization failed

* 404 -- The data product was not found

* 500 -- Server Error

Configuration file
===

Configuration for the transfer service will be loaded from `~/.transferagent.cfg` or, if
this file does not exist, then `transferagent.cfg` in the same directory as the code will
be loaded instead.

The transfer agent operates using SSL, and the following provides information
regarding the credentials to use for running the server:

```
[ssl]
cert = /etc/letsencrypt/live/deliv-prot1.cyberska.org/cert.pem
key = /etc/letsencrypt/live/deliv-prot1.cyberska.org/privkey.pem
chain = /etc/letsencrypt/live/deliv-prot1.cyberska.org/chain.pem
```

X.509 client certificate authentication / authorization is used for all
communication between this transfer agent and the transfer service.

The `credentials` section of the configuration file specifies an X.509 certificate
and key used to authenticate with the transfer service, whereas the `permitted` field
in the `auth` section of the configuration file specifies the X.509 distinguished names
of certificates which will be permitted access (one line per distinguished name).

```
[credentials]
cert = /etc/grid-security/prepare/preparecert.pem
key = /etc/grid-security/prepare/preparekey.pem

[auth]
permitted =
    /O=Grid/OU=GlobusTest/OU=simpleCA-deliv-prot1.cyberska.org/CN=transfer/deliv-prot1.cyberska.org
```

The endpoint section outlines the port on which the service is to be run.  *Note that
at present the transfer service only supports agents run on port 8444, so this value
should not be changed.*

```
[endpoint]
port = 8444
```

The transfer agent ensures that only directories contained within the staged products
areas are permitted.  The `basedir` in the `staged` section of the configuration file

```
[staged]
basedir = /home/ubuntu/staging
```