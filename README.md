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
pip install pika twisted ConfigParser service_identity treq urllib3[secure] \
  pyOpenSSL cryptography idna certifi mysql-python git+https://gitlab.cern.ch/fts/fts-rest
pip install klein # this is only used for the dummy stager
sudo touch /etc/authbind/byport/{80,443}
sudo chmod 500 /etc/authbind/byport/{80,443}
sudo chown `whoami` /etc/authbind/byport/{80,443}
```

Dirs
===
* `legacy`: Contains code from an earlier incarnation that didn't use a DB backend
* `throwaway`: Contains code not meant to be part of the final product
* `throwaway/fail`: Code from abandoned approaches
* `throwaway/working`: Small scale test programs to verify how to implement a particular bit of code in an approved fashion

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

* `job_id`: The UUID for the job, or null if an error occurred.
* `error`: Boolean
* `msg`: A human readable message describing the result of the submission

If successful, the HTTP status code will be 202 (Accepted).  If unsuccessful, a status
code of 400 or higher will be returned.  Note that the application ensures that the URL
is well formed and specifies a GridFTP server.

/transferStatus
---

This function uses the GET method

**Parameters**

* `job_id`: The relevant job ID

**Returns**

JSON with all non-null database fields except for the stager callback code for the job.

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

* `job_id`: Job ID
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

* `ssl` section

  * `cert`: SSL certificate file
  * `key`: SSL key file
  * `chain`: Certificate chain to ensure that the certificate will be trusted

* `mysql` section
  * `hostname`: Hostname of the database server
  * `username` and `password`: Credentials to connect to the database server with
  * `db`: Name of the database

* `ampq` section
  * `hostname`: Hostname of the rabbitmq server
  * `staging_queue`: Name of the queue in which staging requests are to be stored
  * `transfer_queue`: Name of the queue in which transfer requests are to be stored

* `staging` section
  * `concurrent_max`: The maximum number of concurrent staging jobs to allow
  * `server`: URL of the staging server interface
  * `callback`: URL to contact once the staging has been completed

* `fts` section
  * `server`: URL of the FTS server endpoint
  * `proxy`: Location of a valid X.509 proxy certificate to use
  * `concurrent_max`: The maximum number of concurrent transfer tasks allowed
  * `polling_interval`: The interval in seconds between instances in which the FTS
    server is polled.


Database description
===

Note that for now using varchar(255) for the FTS job ID, although this might be a proper UUID
(which the corresponding mysql function stores as a VARCHAR(36)).

```sql
CREATE TABLE jobs (
job_id VARCHAR(36),
product_id TEXT,
status ENUM('SUBMITTED', 'STAGING', 'DONESTAGING', 'TRANSFERRING', 'ERROR', 'SUCCESS') NOT NULL,
detailed_status TEXT,
destination_path TEXT,
submitter TEXT,
fts_jobid VARCHAR(255),
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
PRIMARY KEY (job_id));
```

TODO
===

* Rewrite start to launch using twistd rather than the current config script.

* Support timeouts in case of stager failure

* Ensure that if you have a series of callbacks that a single errback will prevent
  the callback chain from continuing if there's an error in one of the earlier
  callbacks.

* Verify that whenever an error is reported that the database is updated to report this
  as well.

* Make sure that the error timestamp is being set when the job status is being changed
  to ERROR.  May want to do this at the DB level (for the other timestamps as well)

* Update variable and function names in files to reflect their level of privateness

* Maybe update the name of the detailed_status field to extra_status given that it's not
  really used frequently.
  
* Ensure the user credentials are handled better.  For now dependent on environment
  variables and the credentials are not assumed to expire.  This should **not** be run
  in a production environment.

* Better handling of missing values in config file

* Test suite

Known issues
===

* the application doesn't automatically reconnect to rabbit mq in the event that the
  connection to the server is broken.  

* X.509 client identification still isn't working so for now submitter information is
  not collected nor are authentication / authorization checks being done.  Currently
  security is managed by only binding to the loopback interface.

* Note that at the moment the system is dependent on rabbitmq for managing the queues,
  but additional information about tasks is not currently made available there. It seems
  that queuing order can be modified on rabbitmq to enforce some criteria of fairness -
  see e.g., http://nithril.github.io/amqp/2015/07/05/fair-consuming-with-rabbitmq/ - but
  if this were implemented in this prototype then more information than just the job_id
  would likely need to be added to the queues.

* FTS transfers currently use default settings

Notes
===

If you get an Unhandled Error in Deferred where there's no errback for the Deferred,
then you can add the following code to the file involved to ensure that the Exception
will be reported:

```python
import sys
from twisted.python import log

log.startLogging(sys.stdout)
```

Example commands
===

* Submit a job: `curl http://localhost:8080/submitTransfer -d product_id=005 -d destination_path=gsiftp://ubuntu@deliv-prot2.cyberska.org/home/ubuntu`

* Get transfer status: `curl http://localhost:8080/transferStatus?job_id=b8b14f92-e6f3-11e6-8265-fa163e434fb2`