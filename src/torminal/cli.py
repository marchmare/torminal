def add(args) -> None:
    from torminal.config import config

    config.add_query(args.add)
    print("Updated config:")
    print(f"\t ⬩ stop code: {args.add[0]}")
    print(f"\t ⬩ route ID: {args.add[1]}")


def app() -> None:
    from torminal.tui.app import TORminal
    import argparse

    parser = argparse.ArgumentParser("torminal")
    parser.add_argument(
        "--headless",
        help="Enable headless mode. Currently only enables autoscrolling.",
        required=False,
        action="store_true",
    )
    parser.add_argument(
        "-a",
        "--add",
        nargs=2,
        metavar=("[stop_code]", "[route_id]"),
        help="Add new query to config (headless)",
        required=False,
    )
    args = parser.parse_args()

    if args.add:
        add(args)
        exit()

    TORminal(headless=args.headless).run()
