import type { NextRequest } from "next/server";

export const runtime = "nodejs";

const OPERATOR = "J2-INSCOM-Demo";
const API_URL =
  process.env.DEFENSIVE_API_URL ?? "http://127.0.0.1:3001";

export async function POST(request: NextRequest): Promise<Response> {
  let incomingForm: FormData;
  try {
    incomingForm = await request.formData();
  } catch (err) {
    return Response.json(
      { detail: { code: "bad_request", error: String(err) } },
      { status: 400 },
    );
  }

  // Build a new FormData with the image plus stamped fields.
  const outgoing = new FormData();

  const imageEntry = incomingForm.get("image");
  if (!imageEntry) {
    return Response.json(
      { detail: { code: "bad_request", error: "image field missing" } },
      { status: 400 },
    );
  }
  outgoing.append("image", imageEntry as Blob);
  outgoing.set("operator", OPERATOR);
  outgoing.set("source", "verify_tab");

  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/v1/verify`, {
      method: "POST",
      body: outgoing,
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
