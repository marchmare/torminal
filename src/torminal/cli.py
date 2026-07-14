from torminal.gtfs.static import GTFSStaticLoader
from torminal.query import Monitor, Query


def main() -> None:
    print("🚋 TORminal")

    # get lookup dictionaries
    # lookup = load_lookup()
    # print_summary(lookup)
    loader = GTFSStaticLoader(print_update)
    lookup = loader.load()
    query = Query("NARA71", 10, 60)
    monitor = Monitor(lookup)
    result = monitor.poll(query)
    for r in result:
        print("\nDEPARTURE:")
        print(r)


def print_update(progress):
    print(progress)
