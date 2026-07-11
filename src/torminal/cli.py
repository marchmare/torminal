from google.transit import gtfs_realtime_pb2
from .parser import load_lookup, print_summary


def main() -> None:
    print("🚋 TORminal")

    # get lookup dictionaries
    lookup = load_lookup()
    print_summary(lookup)
