import argparse
import configparser
import csv
import json
import logging
import sys

import requests
from folioclient import FolioClient


def error_exit(status, msg):
    """Write error message and exit."""

    sys.stderr.write(msg)
    sys.exit(status)


def read_config(filename: str):
    """Parse the named config file and return an config object."""

    config = configparser.ConfigParser()
    try:
        with open(filename) as conf_file:
            config.read_file(conf_file)
    except FileNotFoundError as err:
        msg = f"{type(err).__name__}: {err}\n"
        error_exit(1, msg)
    except configparser.MissingSectionHeaderError as err:
        msg = f"{type(err).__name__}: {err}\n"
        error_exit(2, msg)
    return config


def parse_args():
    """Parse command line arguments and return a Namespace object."""

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-i",
        "--infile",
        help="Input file (default: stdin)",
        default=sys.stdin,
        type=argparse.FileType("r"),
    )
    parser.add_argument(
        "-o",
        "--outfile",
        help="Output file (truncate if exists, default: stdout)",
        default=sys.stdout,
        type=argparse.FileType("w"),
    )
    parser.add_argument(
        "-C", "--config_file", help="Name of config file", default="config.ini"
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase verbosity level"
    )
    return parser.parse_args()


def parse_data(line):
    """Placeholder function for parsing input data"""
    return line


def process_data(client, data):
    """Placeholder for processing the data"""
    return data


def write_result(out, output):
    """Placeholder for writing output"""
    out.write(output)


def get_item_by_barcode(client: FolioClient, barcode: str) -> dict:
    """
    Look up an item by its barcode and return it as a JSON object.

    As of Kiwi, FOLIO guarantees that item barcodes are unique.

    Args:
        client: FolioClient object
        barcode: string contianing the item barcode

    Returns:
        A dictionary loaded with the item JSON, or None if no item was found.
    """

    path = "/inventory/items"
    query = f'?query=barcode=="{barcode}"'
    res = client.folio_get(path, None, query)

    if res["totalRecords"] == 0:
        return None

    return res["items"][0]


def get_item_by_barcode_safe(client: FolioClient, barcode: str) -> tuple[int, ...]:
    """
    Look up an item by its barcode and return it as a JSON object.

    Usually we expect a single item to be returned from a barcode, or none if there is no match.
    As of Juniper, FOLIO does guarantee that there will not be more than one match on a barcode.
    As the consequences of making an assumption that only one item will be returned are
    uppredectable, we explicitly return the number of items.

    Args:
        client: FolioClient object
        barcode: string contianing the item barcode

    Returns:
        A tuple of (num, object) of the following patterns:
        (0, None): no items were found matching this barcode
        (1, item): one item was found, the expected case; item is a dictionary JSON data.
        (>1, [item0, ...]): more than one item was found, probably need to handle specially
    """

    # return client.folio_get_single_object(path)
    path = "/inventory/items"
    query = f'?query=barcode=="{barcode}"'
    res = client.folio_get(path, None, query)
    items = res["items"]
    n = res["totalRecords"]
    ret_obj = None
    if n == 0:
        pass
    elif n == 1:
        ret_obj = items[0]
    else:
        ret_obj = items
    return (n, ret_obj)


def delete_perm_location(rec):
    """
    Delete the permanentLocation from the input item record.

    Args:
        rec: dictionary loaded from a JSON record

    Returns:
        The old permanentLocation as dictionary if exists, or None.
    """

    return rec.pop("permanentLocation", None)


def put_item(client, item) -> tuple[int, str]:
    """PUT updated item to FOLIO inventory

    Args:
        client: FolioClient
        item: JSON representation of item as a dictionary

    Returns:
        Tuple of HTTP status code and message if error.
    """

    url = f"{client.okapi_url}/inventory/items/{item['id']}"
    req = requests.put(url, headers=client.okapi_headers, data=json.dumps(item))
    return (req.status_code, req.text)


def delete_location_loop(client, in_csv, out_csv):
    """
    Delete permanent item location for all barcodes in the first column

    Iterates over the input file, assumes the barcode is in the first column
    and deletes the permanent location.

    Writes an output row for each barcode.
    """

    for row in in_csv:
        barcode = row[0]
        status_code = 0
        item = get_item_by_barcode(client, barcode)
        if not item:
            msg = f"No item matching barcode {barcode}"
        else:
            old_loc = delete_perm_location(item)
            if not old_loc:
                msg = "Item had no permanentLocation"
            else:
                (status_code, msg) = put_item(client, item)
                if not msg:
                    msg = "old location: " + old_loc["name"]

        out_csv.writerow([barcode, status_code, msg])


def delete_location_loop_safe(client, in_csv, out_csv):
    """
    Delete permanent item location for all barcodes in the first column

    Iterates over the input file, assumes the barcode is in the first column
    and deletes the permanent location.

    This version assumes it is possible to have more than one item per barcode,
    and reports this as something for manual attention.
    """

    for row in in_csv:
        barcode = row[0]
        status_code = 0
        msg = ""
        (n, rec) = get_item_by_barcode_safe(client, barcode)
        if n == 0:
            msg = f"No item matching barcode {barcode}"
        elif n > 1:
            msg = f"{n} items matched barcode {barcode}"
        else:
            old_loc = delete_perm_location(rec)
            if not old_loc:
                msg = "Item had no permanentLocation"
            else:
                (status_code, msg) = put_item(client, rec)

        out_csv.writerow([barcode, status_code, msg])


def main_loop(client, infile, outfile):
    """Sample main loop, loops over input and writes output."""
    for line in infile:
        data = parse_data(line)
        result = process_data(client, data)
        write_result(outfile, result)


def main():
    args = parse_args()
    config = read_config(args.config_file)
    # Logic or function to override config values from the command line arguments would go here

    client = FolioClient(
        config["Okapi"]["okapi_url"],
        config["Okapi"]["tenant_id"],
        config["Okapi"]["username"],
        config["Okapi"]["password"],
    )

    # main_loop(client, args.infile, args.outfile)
    delete_location_loop(
        client,
        csv.reader(args.infile, dialect="excel-tab"),
        csv.writer(args.outfile, dialect="excel-tab"),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
