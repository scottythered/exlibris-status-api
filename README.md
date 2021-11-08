# exLibris-status-api
This project tracks Primo server statuses by parsing [an API provided by Ex Libris](https://knowledge.exlibrisgroup.com/Cross_Product/Knowledge_Articles/RESTful_API_for_Ex_Libris_system_status).

While ultimately helpful, ExL's RESTful system status API returns a mess of data; rather than returning discrete chunks of information about the maintenance status of your server(s), the API provides the same HTML-formatted text sent out via email to server users, wrapped in XML. Depending on maintenance status, the tree structure of the XML fluctuates, either providing empty XML elements, of leaving elements out completely.

The goal of this project is to parse that API status call into something more granular that can be used internally, such as automatically generating a maintenance alert banner in the Primo UI (or your library's website) or notifying unexpected outages via Twitter or Slack.

## How it Works
The project uses the [serverless framework](https://serverless.com/) to spin up two AWS lambdas: one for interacting with the ExL API & storing the parsed data (in a DynamoDB table), and another that creates an endpoint supporting GET requests of the DynamoDB. The former lambda is set to run every 10 minutes. (You can change this in the repo's `serverless.yml` file if you want more or fewer interactions with ExL's API.)

## Requirements
- NodeJS
- Python 3.6+
- AWS access
- Docker (used to compile Python packages in a container before shipping the package to AWS)

### Python Dependencies
- boto3
- requests
- awscli

### Node Dependencies
- serverless
- serverless-python-requirements (a plugin that uses Docker)

## Running/Updating the App locally
1. Download/clone this repository.

2. If you haven't installed serverless yet, run: `npm install -g serverless`

3. Move to the repo directory.

4. Install the plugin: `sls plugin install -n serverless-python-requirements`

5. To deploy this project, you'll need AWS credentials that are configured locally using the `awscli` Python library. Make sure `awscli` is installed ()`pip3 install awscli`) and then run `aws configure`. One at a time, you will enter an AWS Access Key ID, AWS Secret Access Key, server region, and default output format (just use `json`). (If you need help configuring your AWS credentials locally, [this should help](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html#cli-quick-configuration).)

6. Enter your AWS credentials, server region, DynamoDB table name, and [your local time zone's TZ database name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) in `auth.json`. The lambda functions will use these credentials each time they're run.

7. Make sure Docker is also up and running, then run: `sls deploy`. Serverless will run for a while, packaging up your stuff and deploying it to AWS. Eventually you should end up with a message in your CLI like the one below.  

 ![serverless response](https://bitbucket.org/asulibraries/exlibris-status-api/raw/111d148750f655c7fc5a61b20accb6ae1a6c1de4/img/cli.png)

The listed GET endpoint will let you access the data parsed from the ExL API. For example, when no maintenance is scheduled, the result will look like this:

```
{
  "affected_env": "NA",
  "product": "Primo",
  "maintenance": false,
  "service_status": "OK",
  "last_update": "2019-12-17 14:32",
  "maintenance_message": "NA",
  "maintenance_date": "NA",
  "system_id": "Primo MT NA04",
  ...
}
```

But when a maintenance message is posted:

```
{
  "affected_env": "Production",
  "product": "Primo",
  "maintenance": true,
  "service_status": "OK, Maintenance Scheduled",
  "last_update": "2019-12-17 14:27",
  "maintenance_message": "Due to routine maintenance, Library One Search may be unavailable between Nov 09 at 11:00 PM and Nov 10 at 03:00 AM, Phoenix time. We apologize for the inconvenience.",
  "maintenance_date": "2019-11-10 06:00",
  "system_id": "Primo MT NA04",
  ...
}
```

This can be used to, say automatically generate a maintenance banner within primo:

![banner example](https://bitbucket.org/asulibraries/exlibris-status-api/raw/f0aba11e32cd63199401a730c5a3d1f42ac15f8b/img/banner.png)
