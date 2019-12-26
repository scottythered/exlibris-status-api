#!/usr/bin/env python
# coding: utf-8

import re
from lxml import etree
import requests
from datetime import datetime
from dateutil import tz
import boto3
import os
from more_itertools import unique_everseen


def utc_time_now():
    from_zone = tz.gettz("UTC")
    return (datetime.utcnow()).replace(tzinfo=from_zone)


def utc_to_phoenix_time(time):
    from_zone = tz.gettz("UTC")
    to_zone = tz.gettz("America/Phoenix")
    time_zoned = time.replace(tzinfo=from_zone)
    return time_zoned.astimezone(to_zone)


def phoenix_time_now():
    return utc_to_phoenix_time(utc_time_now())


def message_time_parse(text, mode):
    times = re.search(
        "Estimated Start: (.*) UTC Estimated End: (.*) UTC Description:", text
    )
    if mode == "start":
        return datetime.strptime(times.group(1), "%A, %Y-%B-%d %H:%M")
    elif mode == "stop":
        return datetime.strptime(times.group(2), "%A, %Y-%B-%d %H:%M")
    else:
        raise NameError("Time mode not understood")


def changeomatic(raw_input):
    raw_root = etree.fromstring(raw_input)
    api_data = (raw_root.xpath("/exlibriscloudstatus/instance/schedule")[0]).text
    new_list = api_data.split(" Regards, Ex Libris Cloud Services")
    new_list = [i.strip() for i in new_list]
    new_list = [i for i in new_list if i != ""]
    deduped = list(unique_everseen(new_list))
    counter = 1
    revamped_status = ""
    for i in deduped:
        revamped_status = revamped_status + "<match{0}>{1}</match{0}>".format(
            str(counter), deduped[0]
        )
        counter += 1
    new_parsed_exlib_api_status = raw_input.replace(api_data, revamped_status)
    return new_parsed_exlib_api_status


def handler(event, context):
    # get current time, check ExL's api
    now = (utc_to_phoenix_time(utc_time_now())).strftime("%Y-%m-%d %H:%M")
    body = {"act": "get_status", "client": "xml", "envs": "Primo MT NA04"}
    raw_exlib_api_status = (
        requests.post("https://status.exlibrisgroup.com/?page_id=5511", data=body)
    ).text

    # retrieve previous ExL api status in DynamoDB
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=os.environ["region_name"],
        aws_access_key_id=os.environ["access_key"],
        aws_secret_access_key=os.environ["secret_access"],
    )
    table = dynamodb.Table(os.environ["table"])
    response = table.get_item(Key={"product": "Primo"})

    # if status is the same, only change the update date; if different, update entire DynamoDB entry
    if response["Item"]["raw_api_response"] == raw_exlib_api_status:
        table.update_item(
            Key={"product": "Primo"},
            UpdateExpression="SET last_update = :val1",
            ExpressionAttributeValues={":val1": now},
        )
    else:
        parsed_exlib_api_status = (
            raw_exlib_api_status.replace("<br />", "")
            .replace("<b>", "")
            .replace("</b>", "")
            .replace("\\n", " ")
            .replace("\n", " ")
            .replace("\\r", "")
            .replace("\r", "")
        ).strip()
        parsed_exlib_api_status = re.sub(r"\s{2,}", " ", parsed_exlib_api_status)
        parsed_exlib_api_status = re.sub(r"<a[^<]+?>|</a>", "", parsed_exlib_api_status)
        root = etree.fromstring(parsed_exlib_api_status)
        exlib_api_data = (root.xpath("/exlibriscloudstatus/instance")[0]).attrib
        asu_api = {}
        asu_api["system_id"] = exlib_api_data["id"]
        asu_api["system_service"] = exlib_api_data["service"]

        if (
            exlib_api_data["status"] == "OK"
            and len(root.xpath("/exlibriscloudstatus/instance/schedule")) == 0
            and len(root.xpath("/exlibriscloudstatus/instance/message")) == 0
        ):
            asu_api["service_status"] = "OK"
            asu_api["maintenance"] = False
            asu_api["affected_env"] = "NA"
            asu_api["maintenance_start"] = "NA"
            asu_api["maintenance_stop"] = "NA"
            asu_api["maintenance_message"] = "NA"
            asu_api["maintenance_date"] = "NA"

        elif (
            exlib_api_data["status"] == "OK"
            and len(root.xpath("/exlibriscloudstatus/instance/schedule")) == 1
            and len(root.xpath("/exlibriscloudstatus/instance/message")) == 0
        ):
            changed_exlib_api_status = changeomatic(parsed_exlib_api_status)
            new_root = etree.fromstring(changed_exlib_api_status)
            if len(new_root.xpath("/exlibriscloudstatus/instance/schedule/*")) == 1:
                env = re.search(
                    "we will be performing the following maintenance on your (Sandbox|Production) environment",
                    changed_exlib_api_status,
                )
                asu_api["affected_env"] = env.group(1)
                asu_api["service_status"] = "OK, Maintenance Scheduled"
                asu_api["maintenance"] = True
                asu_api["maintenance_start"] = utc_to_phoenix_time(
                    message_time_parse(changed_exlib_api_status, "start")
                )
                asu_api["maintenance_stop"] = utc_to_phoenix_time(
                    message_time_parse(changed_exlib_api_status, "stop")
                )
                asu_api["maintenance_message"] = (
                    "Due to routine maintenance, Library One Search may be unavailable between {0} and {1}, Phoenix time. "
                    "We apologize for the inconvenience.".format(
                        (asu_api["maintenance_start"]).strftime("%b %d at %I:%M %p"),
                        (asu_api["maintenance_stop"]).strftime("%b %d at %I:%M %p"),
                    )
                )
                asu_api["maintenance_date"] = (
                    message_time_parse(changed_exlib_api_status, "start")
                ).strftime("%Y-%m-%dT%H:%M:%SZ")

            elif len(new_root.xpath("/exlibriscloudstatus/instance/schedule/*")) > 1:
                temp = []
                prog = re.compile(r"\d\d-[a-zA-z]{3}-\d{4} UTC \d{1,2}:\d{2}:\d{2}")
                for found in new_root.xpath("/exlibriscloudstatus/instance/schedule/*"):
                    result = prog.match(found.text)
                    dash_stripped = (result[0]).split(" ")[0]
                    time_obj = datetime.strptime(dash_stripped, "%d-%b-%Y")
                    temp.append(time_obj)
                index = temp.index(min(temp))
                earliest_exlib_api_status = (
                    new_root.xpath("/exlibriscloudstatus/instance/schedule/*")[index]
                ).text
                env = re.search(
                    "we will be performing the following maintenance on your (Sandbox|Production) environment",
                    earliest_exlib_api_status,
                )
                asu_api["affected_env"] = env.group(1)
                asu_api["service_status"] = "OK, Maintenance Scheduled"
                asu_api["maintenance"] = True
                asu_api["maintenance_start"] = utc_to_phoenix_time(
                    message_time_parse(earliest_exlib_api_status, "start")
                )
                asu_api["maintenance_stop"] = utc_to_phoenix_time(
                    message_time_parse(earliest_exlib_api_status, "stop")
                )
                asu_api["maintenance_message"] = (
                    "Due to routine maintenance, Library One Search may be unavailable between {0} and {1}, Phoenix time. "
                    "We apologize for the inconvenience.".format(
                        (asu_api["maintenance_start"]).strftime("%b %d at %I:%M %p"),
                        (asu_api["maintenance_stop"]).strftime("%b %d at %I:%M %p"),
                    )
                )
                asu_api["maintenance_date"] = (
                    message_time_parse(earliest_exlib_api_status, "start")
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                asu_api["service_status"] = "OK"
                asu_api["maintenance"] = False
                asu_api["affected_env"] = "NA"
                asu_api["maintenance_start"] = "NA"
                asu_api["maintenance_stop"] = "NA"
                asu_api["maintenance_message"] = "NA"
                asu_api["maintenance_date"] = "NA"

        elif (
            exlib_api_data["status"] == "MAINT"
            and len(root.xpath("/exlibriscloudstatus/instance/message")) == 1
            and len(root.xpath("/exlibriscloudstatus/instance/schedule")) == 1
        ):
            asu_api["service_status"] = "Maintenance In-Progress"
            asu_api["maintenance"] = True
            asu_api["maintenance_start"] = utc_to_phoenix_time(
                message_time_parse(parsed_exlib_api_status, "start")
            )
            asu_api["maintenance_stop"] = utc_to_phoenix_time(
                message_time_parse(parsed_exlib_api_status, "stop")
            )
            asu_api["maintenance_message"] = (
                "Due to routine maintenance, Library One Search may be unavailable between {0} and {1}, Phoenix time. "
                "We apologize for the inconvenience.".format(
                    (asu_api["maintenance_start"]).strftime("%b %d at %I:%M %p"),
                    (asu_api["maintenance_stop"]).strftime("%b %d at %I:%M %p"),
                )
            )
            asu_api["maintenance_date"] = (
                message_time_parse(parsed_exlib_api_status, "start")
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                env = re.search(
                    "on your Primo (Sandbox|Production) environment",
                    parsed_exlib_api_status,
                )
                asu_api["affected_env"] = env.group(1)
            except:
                asu_api["affected_env"] = "NA"

        elif (
            exlib_api_data["status"] == "OK"
            and len(root.xpath("/exlibriscloudstatus/instance/message")) == 1
            and len(root.xpath("/exlibriscloudstatus/instance/schedule")) == 1
            and "The scheduled maintenance on your environment has now finished."
            in (root.xpath("/exlibriscloudstatus/instance/message")[0]).text
        ):
            try:
                regex_pattern = r"\d\d\-[a-zA-z]{3}\-\d{4} UTC \d{1,2}\:\d{2}\:\d{2}"
                matches = re.findall(
                    regex_pattern,
                    (root.xpath("/exlibriscloudstatus/instance/schedule")[0].text),
                )
                if len(matches) >= 1:
                    env = re.search(
                        "we will be performing the following maintenance on your (Sandbox|Production) environment",
                        parsed_exlib_api_status,
                    )
                    asu_api["affected_env"] = env.group(1)
                    asu_api["service_status"] = "OK, Maintenance Scheduled"
                    asu_api["maintenance"] = True
                    asu_api["maintenance_start"] = utc_to_phoenix_time(
                        message_time_parse(parsed_exlib_api_status, "start")
                    )
                    asu_api["maintenance_stop"] = utc_to_phoenix_time(
                        message_time_parse(parsed_exlib_api_status, "stop")
                    )
                    asu_api["maintenance_message"] = (
                        "Due to routine maintenance, Library One Search may be unavailable between {0} and {1}, Phoenix time. "
                        "We apologize for the inconvenience.".format(
                            (asu_api["maintenance_start"]).strftime(
                                "%b %d at %I:%M %p"
                            ),
                            (asu_api["maintenance_stop"]).strftime("%b %d at %I:%M %p"),
                        )
                    )
                    asu_api["maintenance_date"] = (
                        message_time_parse(parsed_exlib_api_status, "start")
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    asu_api["service_status"] = "OK, Maintenance Completed"
                    asu_api["affected_env"] = "NA"
                    asu_api["maintenance"] = False
                    asu_api["maintenance_start"] = "NA"
                    asu_api["maintenance_stop"] = "NA"
                    asu_api["maintenance_message"] = "NA"

            except:
                asu_api["service_status"] = "OK, Maintenance Completed"
                asu_api["affected_env"] = "NA"
                asu_api["maintenance"] = False
                asu_api["maintenance_start"] = "NA"
                asu_api["maintenance_stop"] = "NA"
                asu_api["maintenance_message"] = "NA"

        else:
            asu_api["service_status"] = "unknown"
            asu_api["maintenance"] = "unknown"
            asu_api["affected_env"] = "unknown"
            asu_api["maintenance_start"] = "unknown"
            asu_api["maintenance_stop"] = "unknown"
            asu_api["maintenance_message"] = "unknown"
            asu_api["maintenance_date"] = "unknown"

        table.update_item(
            Key={"product": "Primo"},
            UpdateExpression=(
                "SET last_update = :val1, affected_env = :val2, maintenance = :val3, "
                "maintenance_message = :val4, raw_api_response = :val5, "
                "service_status = :val6, maintenance_date = :val7"
            ),
            ExpressionAttributeValues={
                ":val1": now,
                ":val2": asu_api["affected_env"],
                ":val3": asu_api["maintenance"],
                ":val4": asu_api["maintenance_message"],
                ":val5": raw_exlib_api_status,
                ":val6": asu_api["service_status"],
                ":val7": asu_api["maintenance_date"],
            },
        )
