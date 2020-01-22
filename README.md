# exLibris-status-api
This project tracks Primo server statuses by parsing [an API provided by Ex Libris](https://knowledge.exlibrisgroup.com/Cross_Product/Knowledge_Articles/RESTful_API_for_Ex_Libris_system_status).

While ultimately helpful, ExL's RESTful system status API returns a horrifying mess of data; rather than returning discrete chunks of information about the maintenance status of your server(s), the API provides the same HTML-formatted text sent out via email to server users, wrapped in XML. Depending on maintenance status, the tree structure of the XML fluctuates, either providing empty XML elements, of leaving elements out completely.

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
- lxml
- requests
- awscli
### Node Dependencies
- serverless
- serverless-python-requirements (a plugin that uses Docker)
## How to Use This
1. Download/clone this repository.

2. If you haven't installed serverless yet, run: `npm install -g serverless`

3. Move to the repo directory.

4. Install the Node plugin: `npm install`

5. To deploy this project, you'll need AWS credentials that are configured locally using the `awscli` Python library. Make sure `awscli` is installed ()`pip3 install awscli`) and then run `aws configure`. One at a time, you will enter an AWS Access Key ID, AWS Secret Access Key, server region, and default output format (just use `json`). (If you need help configuring your AWS credentials locally, [this should help](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html#cli-quick-configuration).)

6. Next, for this to work, you'll need to set up a DynamoDB table. Log into AWS and open the DynamoDB product page; under Dashboard, click `Create Table`. Give your table a name, and under Primary key/Partition key, enter `product` as a `string`. Then click `Create Table`.

7. The, we'll need to create a single item (row) in this DB, which will be constantly updated and overwritten. (You'll only have one item (row) here, for now at least, because we're only checking on one product (Primo) and it has one server.) In your new table, click on `Items`, then `Create Item`. In the `Create Item` window, click on the left-hand dropdown and switch the view from `Tree` to `Text`. Tick the `DynamoDB JSON` box and paste the contents of the repo file `dynamo_starter.json` into the window. Click `Save`.

8. Enter your AWS credentials, server region, DynamoDB table name, and [your local time zone's TZ database name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) in `auth.json`. The lambda functions will use these each time the lambdas are run.

9. The Python handler for interacting with the ExL API is by default set to the `Primo MT NA04` server here in `dynamo_updater.py`:

 ```python
 body = {"act": "get_status", "client": "xml", "envs": "Primo MT NA04"}
 raw_exlib_api_status = (
  requests.post("https://status.exlibrisgroup.com/?page_id=5511", data=body)
   ).text
 ```
 You should probably check which server your Primo dev/sandbox instances run on and use that instead!

10. Make sure Docker is also up and running, then run: `sls deploy`

11. Serverless will run for a while, packaging up your stuff and deploying it to AWS. Eventually you should end up with a message in your CLI like the one below.  

 ![serverless response](https://raw.githubusercontent.com/scottythered/exlibris-status-api/master/img/cli.png)

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

![banner example](https://raw.githubusercontent.com/scottythered/exlibris-status-api/master/img/banner.png)

Cool, huh?
