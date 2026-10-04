/**
 * Stateless Streamable HTTP MCP endpoint for ChatGPT custom connections.
 * Authentication uses the same API_KEY as the existing REST API.
 */
export function registerMcp(app, { apiKey, port }) {
  const protocolVersions = new Set(["2025-03-26", "2024-11-05"]);

  const tools = [
    {
      name: "cloud_video_health",
      title: "Check Cloud Video Engine",
      description: "Check whether the Cloud Video Engine service is responding.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
      name: "render_video",
      title: "Render a video",
      description: "Render a motion-graphics MP4 or edit/join HTTPS video clips. Rendering is synchronous and returns a public MP4 URL.",
      inputSchema: {
        type: "object",
        oneOf: [
          {
            type: "object",
            required: ["projectType", "motionProps"],
            additionalProperties: false,
            properties: {
              projectType: { const: "motion" },
              motionProps: {
                type: "object",
                required: ["titles"],
                additionalProperties: false,
                properties: {
                  titles: { type: "array", minItems: 1, maxItems: 8, items: { type: "string", minLength: 1, maxLength: 160 } },
                  primaryColor: { type: "string", pattern: "^#[0-9a-fA-F]{6}$", default: "#6C5CE7" },
                  durationSeconds: { type: "number", minimum: 3, maximum: 30, default: 8 },
                  animationStyle: { type: "string", enum: ["fade", "slide", "zoom"], default: "fade" },
                  subtitle: { type: "string", maxLength: 300 },
                  width: { type: "integer", minimum: 640, maximum: 1920, default: 1920 },
                  height: { type: "integer", minimum: 360, maximum: 1080, default: 1080 },
                  fps: { type: "integer", minimum: 24, maximum: 60, default: 30 }
                }
              }
            }
          },
          {
            type: "object",
            required: ["projectType", "editProps"],
            additionalProperties: false,
            properties: {
              projectType: { const: "edit" },
              editProps: {
                type: "object",
                required: ["clips"],
                additionalProperties: false,
                properties: {
                  clips: {
                    type: "array", minItems: 1, maxItems: 8,
                    items: {
                      type: "object", required: ["url", "endSeconds"], additionalProperties: false,
                      properties: {
                        url: { type: "string", format: "uri", pattern: "^https://" },
                        startSeconds: { type: "number", minimum: 0, default: 0 },
                        endSeconds: { type: "number", exclusiveMinimum: 0 }
                      }
                    }
                  },
                  audioUrl: { type: "string", format: "uri", pattern: "^https://" },
                  audioVolume: { type: "number", minimum: 0, maximum: 1, default: 0.8 },
                  outputWidth: { type: "integer", minimum: 640, maximum: 1920, default: 1920 },
                  outputHeight: { type: "integer", minimum: 360, maximum: 1080, default: 1080 },
                  fps: { type: "integer", minimum: 24, maximum: 60, default: 30 }
                }
              }
            }
          }
        ]
      }
    }
  ];

  app.post("/mcp", async (req, res) => {
    if (!apiKey) {
      return res.status(503).json({ error: "not_configured", message: "API_KEY is not configured." });
    }
    if (req.get("authorization") !== `Bearer ${apiKey}`) {
      return res.status(401).set("WWW-Authenticate", "Bearer").json({ error: "unauthorized", message: "Missing or invalid bearer token." });
    }

    const body = req.body;
    if (!body || typeof body !== "object" || Array.isArray(body) || body.jsonrpc !== "2.0" || typeof body.method !== "string") {
      return res.status(400).json({ jsonrpc: "2.0", id: body?.id ?? null, error: { code: -32600, message: "Invalid JSON-RPC request." } });
    }

    const hasId = Object.prototype.hasOwnProperty.call(body, "id");
    if (!hasId) return res.status(202).end();

    const reply = (result) => res.status(200).type("application/json").json({ jsonrpc: "2.0", id: body.id, result });
    const fail = (code, message) => res.status(200).type("application/json").json({ jsonrpc: "2.0", id: body.id, error: { code, message } });

    try {
      if (body.method === "initialize") {
        const requested = body.params?.protocolVersion;
        const protocolVersion = protocolVersions.has(requested) ? requested : "2025-03-26";
        return reply({
          protocolVersion,
          capabilities: { tools: { listChanged: false } },
          serverInfo: { name: "cloud-video-engine", version: "1.1.0" },
          instructions: "Use cloud_video_health to check service availability. Use render_video to render a motion video or edit clips. Rendering may take time and returns a public MP4 URL."
        });
      }
      if (body.method === "ping") return reply({});
      if (body.method === "tools/list") return reply({ tools });
      if (body.method === "tools/call") {
        const name = body.params?.name;
        const args = body.params?.arguments ?? {};
        if (name === "cloud_video_health") {
          const response = await fetch(`http://127.0.0.1:${port}/health`);
          const data = await response.json();
          return reply({ content: [{ type: "text", text: JSON.stringify(data) }], structuredContent: data, isError: !response.ok });
        }
        if (name === "render_video") {
          const response = await fetch(`http://127.0.0.1:${port}/api/v1/render`, {
            method: "POST",
            headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
            body: JSON.stringify(args)
          });
          const data = await response.json().catch(() => ({ error: "invalid_response" }));
          return reply({
            content: [{ type: "text", text: JSON.stringify(data) }],
            structuredContent: data,
            isError: !response.ok
          });
        }
        return fail(-32602, "Unknown tool name.");
      }
      if (body.method === "notifications/initialized" || body.method.startsWith("notifications/")) {
        return res.status(202).end();
      }
      return fail(-32601, "Method not found.");
    } catch (error) {
      console.error("MCP request failed:", error?.message || error);
      return fail(-32603, "Internal MCP server error.");
    }
  });

  // This server uses stateless Streamable HTTP and does not open SSE streams.
  app.get("/mcp", (_req, res) => res.status(405).set("Allow", "POST").json({ error: "method_not_allowed", message: "Use POST for Streamable HTTP MCP requests." }));
}
