import { createServer, request as createRequest } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const host = "127.0.0.1";
const port = Number(process.env.KUBO_DASHBOARD_PORT || 5173);
const services = {
  iam: new URL(process.env.KUBO_DASHBOARD_IAM_URL || "http://127.0.0.1:8001"),
  compute: new URL(process.env.KUBO_DASHBOARD_COMPUTE_URL || "http://127.0.0.1:8000"),
};
const contentTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".ico", "image/x-icon"],
]);

for (const [service, upstream] of Object.entries(services)) {
  if (!["http:", "https:"].includes(upstream.protocol)) {
    throw new Error(`The ${service} URL must use HTTP or HTTPS.`);
  }
}

function sendJson(response, status, value) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(JSON.stringify(value));
}

function proxyRequest(request, response, url, service) {
  const suffix = url.pathname.slice(`/api/${service}`.length) + url.search;
  const target = new URL(suffix, services[service]);
  const headers = { ...request.headers, host: target.host };
  delete headers.connection;

  const upstreamRequest = createRequest(target, {
    method: request.method,
    headers,
  }, (upstreamResponse) => {
    response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
    upstreamResponse.pipe(response);
  });
  upstreamRequest.setTimeout(15000, () => upstreamRequest.destroy(new Error("upstream timeout")));
  upstreamRequest.on("error", () => {
    if (!response.headersSent) sendJson(response, 502, { detail: `${service} API is unavailable.` });
    else response.destroy();
  });
  request.pipe(upstreamRequest);
}

async function serveStatic(request, response, url) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    sendJson(response, 405, { detail: "Method not allowed." });
    return;
  }
  let pathname;
  try {
    pathname = decodeURIComponent(url.pathname);
  } catch {
    sendJson(response, 400, { detail: "Invalid URL path." });
    return;
  }
  const relativePath = pathname === "/" ? "index.html" : pathname.slice(1);
  const filePath = path.resolve(root, relativePath);
  if (!filePath.startsWith(`${root}${path.sep}`)) {
    sendJson(response, 403, { detail: "Forbidden." });
    return;
  }
  try {
    const body = await readFile(filePath);
    response.writeHead(200, {
      "Content-Type": contentTypes.get(path.extname(filePath)) || "application/octet-stream",
      "Cache-Control": "no-store",
      "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "Referrer-Policy": "no-referrer",
    });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch (error) {
    const notFound = error && typeof error === "object" && "code" in error && error.code === "ENOENT";
    sendJson(response, notFound ? 404 : 500, { detail: notFound ? "Not found." : "Unable to read frontend file." });
  }
}

const server = createServer((request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host || `${host}:${port}`}`);
  const match = url.pathname.match(/^\/api\/(iam|compute)(\/|$)/);
  if (match) {
    proxyRequest(request, response, url, match[1]);
    return;
  }
  void serveStatic(request, response, url);
});

server.listen(port, host, () => {
  console.log(`Kubo dashboard: http://${host}:${port}`);
  console.log(`IAM proxy: ${services.iam.origin} | Compute proxy: ${services.compute.origin}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
