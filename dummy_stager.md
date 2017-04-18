This is a simple stager, *not intended for production use*, but rather for the
purpose of testing the transfer prototype.  This stager simply copies files from
one directory to another without really doing any activity worth the hassle of
separating out this stage.

It accepts incoming API calls at its root URI and then responds back to staging
requests.

Params for (`/`):
===

* `transfer_id` -- ID number of the transfer for the transfer service.

* `product_id` -- ID number of the product to be transferred.

* `callback` -- URL to report the results of the staging to.

Config file:
===

Configuration for the stager will first be searched for in `~/.dummy_stager.cfg`, but
if this file does not exist then `dummy_stager.cfg` in the present directory will be
used instead..

The stager service operates using SSL, and the following provides information
regarding the credentials to use for running the server:

```
[ssl]
cert = /etc/letsencrypt/live/deliv-prot1.cyberska.org/cert.pem
key = /etc/letsencrypt/live/deliv-prot1.cyberska.org/privkey.pem
chain = /etc/letsencrypt/live/deliv-prot1.cyberska.org/chain.pem
```

X.509 client certificate authentication / authorization is used for all
communication between the staging server and the transfer service.

The `credentials` section of the configuration file specifies an X.509 certificate
and key used to authenticate with the transfer service, whereas the `permitted` field
in the `auth` section of the configuration file specifies the X.509 distinguished names
of certificates which will be permitted access (one line per distinguished name).
```
[credentials]
cert = /etc/grid-security/stager/stagercert.pem
key = /etc/grid-security/stager/stagerkey.pem

[auth]
permitted =
    /O=Grid/OU=GlobusTest/OU=simpleCA-deliv-prot1.cyberska.org/CN=transfer/deliv-prot1.cyberska.org
```

The endpoint section outlines the port on which the service is to be run.

```
[endpoint]
port = 8445
```

`source` in the `destination` section of the file specifies a directory which will be
searched for products to transfer, and `destination` specifies where the staged products
will be placed.

```
[directories]
source = /home/ubuntu/products
destination = /home/ubuntu/staging
```