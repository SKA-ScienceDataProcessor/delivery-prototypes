This repo contains code for a transfer prototype for a MeerKAT transfer service.

##Related docs
* [DELIV prototype dev notes](https://docs.google.com/document/d/1Hj6m_Ya_mqGoXOwtQfCGe6KFXjEPXRDKqTrDOS0so7I/edit)
* [FTS setup](https://docs.google.com/document/d/1u6VLhZ6PYIK6yVwheAJqo5kDhm1d3Xz1d7pn1PGUnEk/edit)

##Dirs
* `legacy`: Contains code from an earlier incarnation that didn't use a DB backend
* `throwaway`: Contains code not meant to be part of the final product
* `throwaway/fail`: Code from abandoned approaches
* `throwaway/working`: Small scale test programs to verify how to implement a particular bit of code in an approved fashion

##REST API description

###`/submitTransfer`

Transfers must be submitting using this API call and the POST method.

####Parameters

* `product_id`
* `destination_path`

####Returns

JSON with the following fields:

* `job_id`: The UUID for the job, or null if an error occurred.
* `error`: Boolean
* `msg`: A human readable message describing the result of the submission

If successful, the HTTP status code will be 202 (Accepted).  If unsuccessful, a status
code of 400 or higher will be returned.

###`/transferStatus`

This function uses the GET method

####Parameters

* `job_id`: The relevant job ID

####Returns

JSON with all non-null database fields except for the stager callback code for the job.

#####HTTP status code
* 200: If all is normal
* 400: If missing required parameter
* 403: If not authorized
* 404: If not found
* 500: If an error occurred processing the request

###`/doneStaging`

This is an internal call used to enable the stager to report the completion of staging
tasks.  It currently uses one-time passcodes but should eventually be updated to use
OAuth.

####Parameters
* `product_id`: Product ID
* `jobid`: **Not yet implemented in test stager**
* `authcode`: Authorization code generated when the job was sent to the stager
* `path`: Path at which the staged product was placed

####Returns


##Database description

Note that for now using varchar(255) for the FTS job ID, although this might be a proper UUID
(which the corresponding mysql function stores as a VARCHAR(36)).

```sql

CREATE TABLE jobs (
job_id VARCHAR(36),
product_id TEXT,
status ENUM('SUBMITTED', 'STAGING', 'TRANSFERRING', 'ERROR', 'SUCCESS') NOT NULL,
detailed_status TEXT,
destination_path TEXT,
submitter TEXT,
fts_jobid VARCHAR(255),
fts_details TEXT,
stager_callback VARCHAR(32),
stager_path TEXT,
time_submitted TIMESTAMP NULL,
time_staging TIMESTAMP NULL,
time_transferring TIMESTAMP NULL,
time_error TIMESTAMP NULL,
time_success TIMESTAMP NULL,
PRIMARY KEY (job_id));

```

## Known issues

* the application doesn't automatically reconnect to rabbit mq in the event that the
  connection to the server is broken.

* X.509 client identification still isn't working so for now submitter information is
  not collected nor are authentication / authorization checks being done.  Currently
  security is managed by only binding to the loopback interface.

## Example commands

* Submit a job: curl http://localhost:8080/submitTransfer -d product_id=5 -d destination_path=gsiftp://ubuntu@deliv-prot2.cyberska.org/home/ubuntu

* Get transfer status: curl http://localhost:8080/transferStatus?job_id=b8b14f92-e6f3-11e6-8265-fa163e434fb2