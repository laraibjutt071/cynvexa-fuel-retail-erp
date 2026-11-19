import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  adminEmail: string;
  adminPassword: string;
  orgId: string;
};

async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.fill("#email", state.adminEmail);
  await page.fill("#password", state.adminPassword);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Phase 5b — Super Admin support sessions", () => {
  test("stations/users are locked until a support session is started, then visible, then locked again after ending it", async ({
    page,
  }) => {
    await loginAsAdmin(page);
    await page.goto(`/dashboard/platform/organizations/${state.orgId}`);

    await expect(page.getByText("Start a support session to view this organization's stations.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Start support session" })).toBeVisible();

    await page.getByRole("button", { name: "Start support session" }).click();
    await page.getByLabel("Reason").fill("E2E: verifying the support session flow end to end.");
    await page.getByRole("button", { name: "Start session" }).click();

    await expect(page.getByText(/Support session active/)).toBeVisible();
    await expect(page.getByText("Start a support session to view this organization's stations.")).not.toBeVisible();

    await page.getByRole("button", { name: "End support session" }).click();
    await expect(page.getByText("Start a support session to view this organization's stations.")).toBeVisible();
  });
});
