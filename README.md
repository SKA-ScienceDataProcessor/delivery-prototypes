This repo contains code for a transfer prototype for a MeerKAT transfer service.

Related docs
===
* [DELIV prototype dev notes](https://docs.google.com/document/d/1Hj6m_Ya_mqGoXOwtQfCGe6KFXjEPXRDKqTrDOS0so7I/edit)
* [FTS setup](https://docs.google.com/document/d/1u6VLhZ6PYIK6yVwheAJqo5kDhm1d3Xz1d7pn1PGUnEk/edit)

Installation
===
The installation was developed on Ubuntu 14 LTS, and installation can be done
by following the instructions below:

```
sudo apt-get install python-dev python-virtualenv libssl-dev libffi-dev \
  libmariadbclient-dev mariadb-server mariadb-client libcurl4-gnutls-dev \
  python-m2crypto authbind
virtualenv --system-site-packages venv
. venv/bin/activate
# note that if you don’t use the version of M2Crypto available through apt,
# due to how OpenSSL headers are defined in Ubuntu, you’ll get an SSL error
# when trying to use it if installed by pip
pip install pika twisted ConfigParser service_identity requests urllib3[secure] \
  pyOpenSSL cryptography idna certifi mysql-python git+https://gitlab.cern.ch/fts/fts-rest
pip install klein # this is only used for the dummy stager
sudo touch /etc/authbind/byport/{80,443}
sudo chmod 500 /etc/authbind/byport/{80,443}
sudo chown `whoami` /etc/authbind/byport/{80,443}
```

Launching the service
===

**Stager**
The current stager service is more minimalistic than the version found in the `legacy`
folder.  At present the service is hardcoded to accept as product IDs filenames in the
`~/products` directory and performing the staging account will create a hard link to these
in the `~/staging` directory.  *Note that as this is a minimalistic service intended to
only be accessible on localhost, precautions have not been taken against using relative
paths to access files in other directories.*

```sh
. ~/venv/bin/activate
cd ~/transferprototype
./dummy_stager.py
```

**Transfer tool**
In order for this to work, a MySQL database needs to be setup and a table created as
outlined later in this file. It is also necessary to update the configuration file
to work in your installation, using the config file section later in in the document.
To avoid mixing configuration and code, installs should specify their configuration in
`~/.transfer.cfg` which will replace the default configuration when available.
```sh
. ~/venv/bin/activate
cd ~/transferprototype
./transfer.py
```

Dirs
===
* `legacy`: Contains code from an earlier incarnation that didn't use a DB backend
* `throwaway`: Contains code not meant to be part of the final product.  Used for prototyping new additions to the codebase.

REST API description
===

/submitTransfer
---

Transfers must be submitted using this API call and the POST method.

For a transfer request to be accepted the X.509 distinguished name of the certificate
used must be listed as one of the `permitted` certificates in the `auth` section of
the configuration file.

**Parameters**

* `product_id`
* `destination_path`: A directory in which the resulting file is to be deposited
* `prepare`: Details of any preprocessing to be done

**Returns**

JSON with the following fields:

* `transfer_id`: The UUID for the transfer, or null if an error occurred.
* `error`: Boolean
* `msg`: A human readable message describing the result of the submission

If successful, the HTTP status code will be 202 (Accepted).  If unsuccessful, a status
code of 400 or higher will be returned.  Note that the application ensures that the URL
is well formed and specifies a GridFTP server.

/transferStatus
---

This function uses the GET method.

Requests are only authorized if using the same certificate as when they made the
original submission.

**Parameters**

* `transfer_id`: The relevant transfer ID

**Returns**

JSON with all database fields

**HTTP status code**

* 200: If all is normal
* 400: If missing required parameter
* 403: If not authorized
* 404: If not found
* 500: If an error occurred processing the request

/donePrepare
---

This is an internal call used to enable the prepare system to report the completion
of preprocessing. It allows requests to use either GET or POST methods.

Note that in order to post to this URL the certificate corresponding to the X.509
distinguished name listed in the `prepare` section of the config file as `x509dn` must
be used when making the request.

**Parameters**

* `transfer_id`: Transfer ID
* `success`: A boolean indicating whether or not the product ID was successfully staged
* `msg`: A text message from the stager indicating the results of the request

**HTTP status code**

* 200: If all is normal
* 400: If parameters were invalid
* 403: If the request was unauthorized
* 500: If there was an error detecting when processing the report


/doneStaging
---

This is an internal call used to enable the stager to report the completion of staging
tasks. It allows requests to use either GET or POST methods.

Note that in order to post to this URL the certificate corresponding to the X.509
distinguished name listed in the `staging` section of the config file as `x509dn` must
be used when making the request.

**Parameters**

* `transfer_id`: Transfer ID
* `product_id`: Product ID
* `success`: A boolean indicating whether or not the product ID was successfully staged
* `staged_to`: Hostname of the GridFTP server the product was staged to
* `path`: Path at which the staged product was placed
* `msg`: A text message from the stager indicating the results of the request

**HTTP status code**

* 200: If all is normal
* 400: If parameters were invalid
* 403: If the request was unauthorized
* 500: If there was an error detecting when processing the report


Configuration file
===

The application looks for its configuration file first at `~/.transfer.cfg`, and if this
fails instead uses the file `transfer.cfg` in the application directory.

The application uses [ConfigParser](https://docs.python.org/2/library/configparser.html)
with its INI-style formatting of the file.  It has the following fields:

* `auth` section

    * `permitted`: X.509 distinguished names permitted to use the service (one
      per line)

* `ssl` section

    * `cert`: SSL certificate file
    * `key`: SSL key file
    * `chain`: Certificate chain to ensure that the certificate will be trusted

* `mysql` section

    * `hostname`: Hostname of the database server
    * `username` and `password`: Credentials to connect to the database server with
    * `db`: Name of the database

* `amqp` section

    * `uri`: URI to use to connect to the = amqp://localhost
    * `prepare_queue`: Name of the queue in which preprocessing requests are to be stored
    * `staging_queue`: Name of the queue in which staging requests are to be stored
    * `transfer_queue`: Name of the queue in which transfer requests are to be stored

* `staging` section

    * `concurrent_max`: The maximum number of concurrent staging tasks to allow
    * `server`: URL of the staging server interface
    * `callback`: URL to contact once the staging has been completed
    * `x509dn`: X.509 distinguished name of the certificate used by the stager to
      communicate with the server
    * `cert`: Path to an X.509 certificate to use
    * `key`: Path to key for certificate

* `fts` section

    * `server`: URL of the FTS server endpoint
    * `cert`: Path to an X.509 certificate to use
    * `key`: Path to key for certificate
    * `concurrent_max`: The maximum number of concurrent transfer tasks allowed
    * `polling_interval`: The interval in seconds between instances in which the FTS
      server is polled.

* `prepare` section

    * `concurrent_max`: The maximum number of preprocessing tasks that can take place simultaneously
    * `server`: URL of the staging server interface
    * `callback`: URL to contact once the staging has been completed
    * `x509dn`: X.509 distinguished name of the certificate used by the stager to
      communicate with the server
    * `cert`: Path to an X.509 certificate to use
    * `key`: Path to key for certificate

Database description
===

Note that for now using varchar(255) for the FTS ID, although this might be a proper UUID
(which the corresponding mysql function stores as a VARCHAR(36)).

```sql
CREATE TABLE transfers (
transfer_id VARCHAR(36),
product_id TEXT,
status ENUM('INIT', 'SUBMITTED', 'STAGING', 'STAGINGDONE', 'PREPARING', 'PREPARINGDONE', 'TRANSFERRING', 'ERROR', 'SUCCESS') NOT NULL,
extra_status TEXT,
destination_path TEXT,
submitter TEXT,
fts_id VARCHAR(255),
fts_details TEXT,
stager_path TEXT,
stager_hostname TEXT,
stager_status TEXT,
prepare_activity TEXT,
time_submitted TIMESTAMP NULL,
time_staging TIMESTAMP NULL,
time_staging_done TIMESTAMP NULL,
time_preparing TIMESTAMP NULL,
time_preparing_done TIMESTAMP NULL,
time_transferring TIMESTAMP NULL,
time_error TIMESTAMP NULL,
time_success TIMESTAMP NULL,
PRIMARY KEY (transfer_id));

# Ensure that timestamps are updated
delimiter //
CREATE TRIGGER update_transfer_timestamps BEFORE UPDATE ON transfers
FOR EACH ROW
BEGIN
    IF NEW.status = 'SUBMITTED' THEN
        SET NEW.time_submitted = NOW();
    ELSEIF NEW.status = 'STAGING' THEN
        SET NEW.time_staging = NOW();
    ELSEIF NEW.status = 'STAGINGDONE' THEN
        SET NEW.time_staging_done = NOW();
    ELSEIF NEW.status = 'PREPARING' THEN
        SET NEW.time_preparing = NOW();
    ELSEIF NEW.status = 'PREPARINGDONE' THEN
        SET NEW.time_preparing_done = NOW();
    ELSEIF NEW.status = 'TRANSFERRING' THEN
        SET NEW.time_transferring = NOW();
    ELSEIF NEW.status = 'ERROR' THEN
        SET NEW.time_error = NOW();
    ELSEIF NEW.status = 'SUCCESS' THEN
        SET NEW.time_success = NOW();
    END IF;
END;//
delimiter ;
```

TODO
===

* Add a basic product catalog verification service, which basically will tell you if
  a product exists and, if so, what its size is (to better support QoS policies).

* Transfer requests would likely need to start including information about a project
  with which the transfer request is to be associated.


Known issues
===

* Note that at the moment the system is dependent on rabbitmq for managing the queues,
  but additional information about tasks is not currently made available there. It seems
  that queuing order can be modified on rabbitmq to enforce some criteria of fairness -
  see e.g., http://nithril.github.io/amqp/2015/07/05/fair-consuming-with-rabbitmq/ - but
  if this were implemented in this prototype then more information than just the
  transfer_id would likely need to be added to the queues.

* It seems annoying cumbersome to work with multiple threads in twisted.  i.e. pretty
  much none of the packages used are threadsafe including twisted (which fairly
  significantly restricts the amount of parallelism which can works.

* FTS transfers currently use default settings.  It may be necessary to alter these settings
  or perhaps even alter FTS or the underlying GFAL plugin for GridFTP as ASTRON's firewall
  apparently permits only passive transfers.

* The transfer service currently assumes that all preprocessing servers runs on port
  8444.  The configuration file for the preprocessing service allows a different port
  to be specified but that is *not* presently supported by the service.

Example commands
===

* Submit a transfer:
```sh
# Get product ID 005
curl https://deliv-prot1.cyberska.org:8443/submitTransfer -d product_id=005 \
    -d destination_path=gsiftp://ubuntu@deliv-prot2.cyberska.org/home/ubuntu/staged \
    -E /tmp/x509up_u1000
```

* Get transfer status:
```sh
# Get status of transfer b8b14f92-e6f3-11e6-8265-fa163e434fb2
curl https://deliv-prot1.cyberska.org:8443/transferStatus?transfer_id=b8b14f92-e6f3-11e6-8265-fa163e434fb2 \
     -E /tmp/x509up_u1000
```