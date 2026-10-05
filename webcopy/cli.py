import argparse
import json
import sys
from pathlib import Path
from .engine import Archive, Options


def atomic_status(path, state):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description="Web Copy Lite — archive authorized public websites")
    parser.add_argument("url", nargs="?")
    parser.add_argument("--output", default="output/archive")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--max-resources", type=int, default=500)
    parser.add_argument("--user-agent", default=Options.user_agent)
    parser.add_argument("--ignore-robots", action="store_true", help="Use only with site owner's explicit authorization")
    parser.add_argument("--render", action="store_true", help="Capture a rendered DOM with optional Playwright")
    parser.add_argument("--job", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    status_path = None
    try:
        if args.job:
            config = json.loads(args.job.read_text(encoding="utf-8"))
            options = Options(**config["options"])
            output = args.job.parent
            status_path = output / "status.json"
        else:
            if not args.url:
                parser.error("url is required")
            options = Options(args.url, depth=args.depth, workers=args.workers, delay=args.delay,
                              max_resources=args.max_resources, user_agent=args.user_agent,
                              respect_robots=not args.ignore_robots, render=args.render)
            output = Path(args.output)
        def progress(state):
            if status_path:
                atomic_status(status_path, state)
            else:
                print("\r{}: {} copied · {} failed · {} queued".format(state["status"], state["copied"], state["failed"], state["queued"]), end="", flush=True)
        archive = Archive(options, output, progress=progress)
        result = archive.run()
        if not status_path:
            print("\nArchive: {}".format(result.resolve()))
        return 0
    except Exception as exc:
        if status_path:
            state = archive.state() if "archive" in locals() else {"copied": 0, "failed": 0, "logs": []}
            state.update(status="failed", error=str(exc))
            atomic_status(status_path, state)
        print("\nError: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
