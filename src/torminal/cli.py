from .gtfs import load_lookup, print_summary
from .query import Monitor, Query


def main() -> None:
    print("🚋 TORminal")

    # get lookup dictionaries
    lookup = load_lookup()
    print_summary(lookup)

    query = Query(4008, 10, 60)
    monitor = Monitor(lookup)
    result = monitor.poll(query)
    for r in result:
        print("\nDEPARTURE:")
        print(r)
