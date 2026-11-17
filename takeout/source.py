"""Read-only Codex app-server client. No turn execution or approval APIs."""
import json
import queue
import subprocess
import threading


class CodexSource:
    def __init__(self, executable="codex", timeout=60):
        self.timeout = timeout
        self.counter = 0
        self.process = subprocess.Popen(
            [executable, "app-server", "--stdio"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        self.messages = queue.Queue()

        def consume():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    continue
            self.messages.put(None)

        threading.Thread(target=consume, daemon=True).start()
        try:
            self.identity = self.call("initialize", {
                "clientInfo": {"name": "takeout", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            })
            self.send({"method": "initialized"})
        except BaseException:
            self.close()
            raise

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def call(self, method, params):
        self.counter += 1
        request_id = self.counter
        self.send({"id": request_id, "method": method, "params": params})
        while True:
            try:
                message = self.messages.get(timeout=self.timeout)
            except queue.Empty:
                raise RuntimeError("Codex app-server response timed out")
            if message is None:
                raise RuntimeError("Codex app-server closed its output")
            if "method" in message and "id" in message:
                self.send({"id": message["id"], "error": {
                    "code": -32601, "message": "takeout is a read-only client"}})
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise RuntimeError("%s: %s" % (method, message["error"]))
                return message["result"]

    def pages(self, method, params):
        seen = set()
        cursor = None
        while True:
            page = self.call(method, dict(params, cursor=cursor))
            yield from page["data"]
            cursor = page.get("nextCursor")
            if not cursor:
                return
            if cursor in seen:
                raise RuntimeError("Source repeated a pagination cursor")
            seen.add(cursor)

    def list_threads(self):
        return list(self.pages("thread/list", {"limit": 100}))

    def pages(self, method, params):
        params = dict(params)
        seen = set()
        while True:
            page = self.call(method, params)
            yield from page["data"]
            cursor = page.get("nextCursor")
            if not cursor:
                return
            if cursor in seen:
                raise RuntimeError("Source repeated a pagination cursor")
            seen.add(cursor)
            params["cursor"] = cursor

    def read_thread(self, thread_id):
        thread = self.call("thread/read", {"threadId": thread_id, "includeTurns": False})["thread"]
        turns = list(self.pages("thread/turns/list", {
            "threadId": thread_id, "limit": 100, "sortDirection": "asc", "itemsView": "full"}))
        # Full itemsView is explicitly guaranteed by the negotiated installed protocol.
        for turn in turns:
            if turn.get("itemsView", "full") != "full":
                raise RuntimeError("Source did not return full turn history")
        thread["turns"] = turns
        return {"thread": thread, "source": "codex-app-server", "server": self.identity}

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
