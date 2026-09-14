import http from "node:http";

const target = new URL(process.env.PLAYWRIGHT_PROXY_TARGET || "http://web:3000");

const server = http.createServer((request, response) => {
  const upstream = http.request(
    {
      hostname: target.hostname,
      port: target.port || 80,
      path: request.url,
      method: request.method,
      headers: request.headers,
    },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    },
  );

  upstream.on("error", (error) => {
    if (!response.headersSent) {
      response.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    }
    response.end(`CI proxy could not reach the web service: ${error.message}`);
  });

  request.pipe(upstream);
});

server.listen(3000, "127.0.0.1");

function shutdown() {
  server.close(() => process.exit(0));
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
