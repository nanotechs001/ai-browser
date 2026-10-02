"""Token-guarded proxy in front of Chromium's DevTools port, inside the browser container.

Only requests whose path starts with /<AIB_TOKEN>/ are forwarded (with that prefix removed);
everything else gets 403. The token is known only to the ai-browser engine on the host.
"""

import asyncio
import hmac
import os
import sys

TOKEN = os.environ["AIB_TOKEN"].encode()
LISTEN_PORT, CHROME_PORT = int(sys.argv[1]), int(sys.argv[2])
FORBIDDEN = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    try:
        head = await asyncio.wait_for(client_reader.readuntil(b"\r\n\r\n"), timeout=10)
        line_end = head.index(b"\r\n")
        method, path, version = head[:line_end].split(b" ", 2)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError):
        client_writer.close()
        return
    segment, _, rest = path.lstrip(b"/").partition(b"/")
    if not hmac.compare_digest(segment, TOKEN):
        client_writer.write(FORBIDDEN)
        await client_writer.drain()
        client_writer.close()
        return
    upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", CHROME_PORT)
    upstream_writer.write(method + b" /" + rest + b" " + version + head[line_end:])
    await upstream_writer.drain()
    await asyncio.gather(pipe(client_reader, upstream_writer), pipe(upstream_reader, client_writer))


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", LISTEN_PORT)
    async with server:
        await server.serve_forever()


asyncio.run(main())
