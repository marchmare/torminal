from .gtfs_static import load_lookup, print_summary
from .query import Query


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
    result = query.poll(time_window=60)
    for r in result:
        print("\nDEPARTURE:")
        for k, v in r.items():
            if k.startswith("_"):
                continue
            print(f"{k}: {v}")

    # print(get_gtfs_rt_data())
