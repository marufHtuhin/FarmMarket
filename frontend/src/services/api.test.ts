import { describe, expect, it } from "vitest";
import { parseSseEvents } from "./api";

describe("parseSseEvents", () => {
  it("parses data events and keeps the incomplete tail", () => {
    const { events, rest } = parseSseEvents(
      'data: {"text":"Hello "}\n\ndata: {"text":"wor'
    );
    expect(events).toEqual([{ type: "message", data: '{"text":"Hello "}' }]);
    expect(rest).toBe('data: {"text":"wor');
  });

  it("parses named events and ignores comments", () => {
    const { events, rest } = parseSseEvents(
      ": ping\n\nevent: done\ndata: {\"mode\":\"gemini\"}\n\n"
    );
    expect(events).toEqual([{ type: "done", data: '{"mode":"gemini"}' }]);
    expect(rest).toBe("");
  });

  it("joins multi-line data blocks and resumes across chunks", () => {
    const first = parseSseEvents('event: error\ndata: {"err');
    expect(first.events).toEqual([]);
    const second = parseSseEvents(first.rest + 'or":"boom"}\n\n');
    expect(second.events).toEqual([{ type: "error", data: '{"error":"boom"}' }]);
    expect(second.rest).toBe("");
  });

  it("returns no events for an empty buffer", () => {
    expect(parseSseEvents("")).toEqual({ events: [], rest: "" });
  });
});
