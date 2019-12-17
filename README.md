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
## Instructions
1. Download/clone this repository.

2. If you haven't installed serverless yet, run: `npm install -g serverless`

3. Move to the repo directory.

4. Install the Node plugin: `npm install`

5. To deploy this project, you'll need AWS credentials that are configured locally using the `awscli` Python library. Make sure `awscli` is installed ()`pip3 install awscli`) and then run `aws configure`. One at a time, you will enter an AWS Access Key ID, AWS Secret Access Key, server region, and default output format (just use `json`). (If you need help configuring your AWS credentials locally, [this should help](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html#cli-quick-configuration).)

6. Next, for this to work, you'll need to set up a DynamoDB table. Log into AWS and open the DynamoDB product page; under Dashboard, click `Create Table`. Give your table a name, and under Primary key/Partition key, enter `product` as a `string`. Then click `Create Table`.

7. The, we'll need to create a single item (row) in this DB, which will be constantly updated and overwritten. (You'll only have one item (row) here, for now at least, because we're only checking on one product (Primo) and it has one server.) In your new table, click on `Items`, then `Create Item`. In the `Create Item` window, click on the left-hand dropdown and switch the view from `Tree` to `Text`. Tick the `DynamoDB JSON` box and paste the contents of the repo file `dynamo_starter.json` into the window. Click `Save`.

8. Enter your AWS credentials, server region, and DynamoDB table name in `auth.json`. The lambda functions will use these credentials each time they're run.

9. The Python handler for interacting with the ExL API is by default set to the `Primo MT NA04` server here in `dynamo_updater.py`:

 ```python
 body = {"act": "get_status", "client": "xml", "envs": "Primo MT NA04"}
 raw_exlib_api_status = (
  requests.post("https://status.exlibrisgroup.com/?page_id=5511", data=body)
   ).text
 ```
 You should probably check which server your Primo dev/sandbox instances run on and use that instead!

10. Make sure Docker is also up and running, then run: `sls deploy`

13. Serverless will run for a while, packaging up your stuff and deploying it to AWS. Eventually you should end up with a message in your CLI like the one below.  

 ![serverless response](https://bitbucket.org/asulibraries/exlibris-status-api/raw/111d148750f655c7fc5a61b20accb6ae1a6c1de4/img/cli.png)

The listed GET endpoint will let you access the data parsed from the ExL API. Depending on how often you've set it to run, you can now call this endpoint and get updated, parsed data about your Primo servers.

Cool, huh?
