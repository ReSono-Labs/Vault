"""Short-lived bounded document decoding; no provider, storage or tool authority."""
import json
import sys


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    from .attachments import MAX_FILE_BYTES, inspect_input
    try:
        raw=sys.stdin.buffer.read(MAX_FILE_BYTES+1)
        result=inspect_input(sys.argv[1],raw)
        sys.stdout.write(json.dumps(result,ensure_ascii=True))
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
