export const runtime = "nodejs";

const API_URL = process.env.DEFENSIVE_API_URL ?? "http://127.0.0.1:3001";

export async function GET(): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/v1/recent?limit=10`, {
      cache: "no-store",
    });
  } catch (err) {
    return Response.json(
      {
        detail: {
          code: "api_unreachable",
          error: err instanceof Error ? err.message : String(err),
        },
      },
      { status: 503 },
    );
  }

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
