from google.transit import gtfs_realtime_pb2
from .parser import load_lookup, print_summary
from .query import Query
from datetime import timedelta, datetime, date


def main() -> None:
    print("🚋 TORminal")

    # get lookup dictionaries
    lookup = load_lookup()
    print_summary(lookup)

    # user input
    # uinput = input("Specify a stop and line to monitor (syntax: <stop>:<line number>:<destination>): ")
    uinput = "NARA71:10"
    stop, line = uinput.split(":")
    query = Query(stop, line, lookup)
    query.poll(minutes=60)
