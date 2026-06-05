import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppRuntimeProviders } from "../app/providers/AppProviders";
import { ErrorBoundary } from "../shared/ui";

const mockGetAppConfig = vi.hoisted(() => vi.fn());

vi.mock("../entities/config/repository", () => ({
  configQueryKey: ["config"],
  getAppConfig: () => mockGetAppConfig(),
}));

vi.mock("../entities/files/repository", () => ({
  browseFiles: vi.fn(),
}));

function renderRuntimeProviders() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ErrorBoundary>
        <AppRuntimeProviders>
          <div>Runtime ready</div>
        </AppRuntimeProviders>
      </ErrorBoundary>
    </QueryClientProvider>,
  );
}

describe("AppRuntimeProviders", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    mockGetAppConfig.mockReset();
    document.documentElement.style.removeProperty("--theme-accent");
    consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it("keeps rendering when the preview config omits system_config", async () => {
    mockGetAppConfig.mockResolvedValue({});

    renderRuntimeProviders();

    expect(await screen.findByText("Runtime ready")).toBeInTheDocument();
    await waitFor(() => expect(mockGetAppConfig).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(consoleError).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(document.documentElement.style.getPropertyValue("--theme-accent")).toBe("#d4788e");
  });
});
