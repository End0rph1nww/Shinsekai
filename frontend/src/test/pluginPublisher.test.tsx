import { afterEach, describe, expect, it, vi } from "vitest";

import { createHttpPlatform } from "../shared/platform/httpPlatform";
import type { PluginSubmissionInput } from "../shared/platform/types";

function mockJsonResponse(body: unknown, ok = true) {
  return Promise.resolve({
    json: () => Promise.resolve(body),
    ok,
    status: ok ? 200 : 400,
    statusText: ok ? "OK" : "Bad Request",
  } as Response);
}

const submission: PluginSubmissionInput = {
  author: "End0rph1nww",
  desc: "Cloud TTS plugin",
  display_name: "Cloud TTS",
  entry: "plugins.cloud_tts.plugin:CloudTTSPlugin",
  repo: "https://github.com/End0rph1nww/shinsekai-cloud-tts",
  social_link: "https://github.com/End0rph1nww",
  tags: ["tts", "cloud"],
};

describe("plugin publisher bridge", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses publisher bridge endpoints for scan, validate, and issue URL generation", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() =>
        mockJsonResponse({
          ...submission,
          logo: "",
          path: "D:/plugins/cloud-tts",
          requirements: "requirements.txt",
          warnings: [],
        }),
      )
      .mockImplementationOnce(() => mockJsonResponse({ errors: [], json: "{}", ok: true, submission }))
      .mockImplementationOnce(() =>
        mockJsonResponse({
          issueUrl: "https://github.com/End0rph1nww/Shinsekai-Plugin-Registry/issues/new?template=PLUGIN_PUBLISH.yml",
          json: "{}",
          submission,
          submitUrl: "https://github.com/End0rph1nww/Shinsekai-Plugin-Registry/issues/new?template=PLUGIN_PUBLISH.yml",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const platform = createHttpPlatform("http://127.0.0.1:8787");
    await platform.plugins.scanLocal({ path: "D:/plugins/cloud-tts" });
    await platform.plugins.validateSubmission(submission);
    await platform.plugins.buildSubmissionIssueUrl(submission);

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://127.0.0.1:8787/api/plugins/publisher/scan",
      "http://127.0.0.1:8787/api/plugins/publisher/validate",
      "http://127.0.0.1:8787/api/plugins/publisher/issue-url",
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ path: "D:/plugins/cloud-tts" });
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual(submission);
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual(submission);
  });

  it("copies the backend payload text to the browser clipboard", async () => {
    const clipboardText = JSON.stringify(submission, null, 2);
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        mockJsonResponse({
          clipboardText,
          json: clipboardText,
          message: "copied",
          submission,
        }),
      ),
    );

    const platform = createHttpPlatform("http://127.0.0.1:8787");
    const result = await platform.plugins.copySubmissionJson(submission);

    expect(result.clipboardText).toBe(clipboardText);
    expect(writeText).toHaveBeenCalledWith(clipboardText);
  });
});
