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

**Parameters**

* `product_id`
* `destination_path`: A directory in which the resulting file is to be deposited

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

This function uses the GET method

**Parameters**

* `transfer_id`: The relevant transfer ID

**Returns**

JSON with all non-null database fields except for the stager callback code for the transfer.

**HTTP status code**

* 200: If all is normal
* 400: If missing required parameter
* 403: If not authorized
* 404: If not found
* 500: If an error occurred processing the request

/doneStaging
---

This is an internal call used to enable the stager to report the completion of staging
tasks. It allows requests to use either GET or POST methods.

**Parameters**

* `transfer_id`: Transfer ID
* `product_id`: Product ID
* `authcode`: Authorization code generated when the task was sent to the stager
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
    * `staging_queue`: Name of the queue in which staging requests are to be stored
    * `transfer_queue`: Name of the queue in which transfer requests are to be stored

* `staging` section

    * `concurrent_max`: The maximum number of concurrent staging tasks to allow
    * `server`: URL of the staging server interface
    * `callback`: URL to contact once the staging has been completed

* `fts` section

    * `server`: URL of the FTS server endpoint
    * `cert`: Path to an X.509 certificate to use
    * `key`: Path to key for certificate
    * `concurrent_max`: The maximum number of concurrent transfer tasks allowed
    * `polling_interval`: The interval in seconds between instances in which the FTS
      server is polled.


Database description
===

Note that for now using varchar(255) for the FTS ID, although this might be a proper UUID
(which the corresponding mysql function stores as a VARCHAR(36)).

```sql
CREATE TABLE transfers (
transfer_id VARCHAR(36),
product_id TEXT,
status ENUM('INIT', 'SUBMITTED', 'STAGING', 'DONESTAGING', 'TRANSFERRING', 'ERROR', 'SUCCESS') NOT NULL,
extra_status TEXT,
destination_path TEXT,
submitter TEXT,
fts_id VARCHAR(255),
fts_details TEXT,
stager_callback VARCHAR(32),
stager_path TEXT,
stager_hostname TEXT,
stager_status TEXT,
time_submitted TIMESTAMP NULL,
time_staging TIMESTAMP NULL,
time_staging_finished TIMESTAMP NULL,
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
    ELSEIF NEW.status = 'DONESTAGING' THEN
        SET NEW.time_staging_finished = NOW();
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

* Rewrite start to launch using twistd rather than the current script.

* Ensure that if you have a series of callbacks that a single errback will prevent
  the callback chain from continuing if there's an error in one of the earlier
  callbacks.

* Verify that whenever an error is reported that the database is updated to report this
  as well.

* Better handling of missing values in config file

* Add a context manager bit to ensure that we're not accumulating too many channels

* Test suite

* Add a basic product catalog verification service, which basically will tell you if
  a product exists and, if so, what its size is (to better support QoS policies).

* Transfer requests would likely need to start including information about a project
  with which the transfer request is to be associated.

* Move to a distributed semaphore of some sort limiting transfers?  (If we'd be using
  a cluster of these servers, what should be enforced on a per-node basis and what on a
  project-wide basis?).

* Double check to ensure that a message can't be lost due to being ACKed before finished
  processing.

* Support timeouts in case of stager failure. Note that additional resiliency might
  require adding some degree of support for state representation in the stager.
  It might also be best to do this using [RabbitMQ's delayed messages plugin](https://www.rabbitmq.com/blog/2015/04/16/scheduling-messages-with-rabbitmq/).

* Update staging process to allow for a `prepare` step, allowing simple computations
  like averaging to be conducted on the data being staging.

* Add an additional state which maintains information about which transfer tasks still
  have files left on the staging nodes.

* No notifications are sent anywhere to indicate that the transfers have completed.

* Support multiple product IDs for a single transfer request

* Tracking / enforcing X.509 auth remains to be done though the system now runs on both
  ports 8080 and 8443.

Known issues
===

* The semaphore's state is not saved when exiting the program, and thus errors may
  occur.

* the application doesn't automatically reconnect to rabbit mq in the event that the
  connection to the server is broken.  A previous attempt at introducing a package
  providing a connection pool was unsuccessful.

* Note that at the moment the system is dependent on rabbitmq for managing the queues,
  but additional information about tasks is not currently made available there. It seems
  that queuing order can be modified on rabbitmq to enforce some criteria of fairness -
  see e.g., http://nithril.github.io/amqp/2015/07/05/fair-consuming-with-rabbitmq/ - but
  if this were implemented in this prototype then more information than just the
  transfer_id would likely need to be added to the queues.

* It seems annoying cumbersome to work with multiple threads in twisted.  i.e. pretty
  much none of the packages used are threadsafe including twisted (which fairly
  significantly restricts the amount of parallelism which can works.

* FTS transfers currently use default settings

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
curl http://localhost:8080/transferStatus?transfer_id=b8b14f92-e6f3-11e6-8265-fa163e434fb2
```