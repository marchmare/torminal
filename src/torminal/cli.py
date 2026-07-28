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
    args = parser.parse_args()

    TORminal(headless=args.headless).run()
