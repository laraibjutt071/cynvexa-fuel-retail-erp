import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Phase 10B — Supplier Invoice & Payment UI. Uses the real backend
 * endpoints end to end (create supplier, record invoice, record payment,
 * approve payment) - no mocking. Suppliers are organization-wide (no
 * station concept on the model), so this doesn't need the station
 * switcher or a dedicated station fixture.
 */

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  ownerEmail: string;
  ownerPassword: string;
  orgId: string;
  roles: {
    cashier: { email: string; password: string };
    accountant: { email: string; password: string };
  };
};

async function loginAs(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Phase 10B — Supplier invoices and payments", () => {
  test("a supplier can be created, invoiced, paid and the balance tracks correctly end to end", async ({ page }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/suppliers`);
    await expect(page.getByRole("heading", { name: "Suppliers" })).toBeVisible();

    const supplierName = `E2E Fuel Supplier ${Date.now().toString(36)}`;

    await page.getByRole("button", { name: "Add supplier" }).click();
    await page.getByRole("dialog").getByLabel("Name").fill(supplierName);
    await page.getByRole("dialog").getByLabel("Phone").fill("0300-1234567");
    await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();

    const row = page.locator("table tbody tr", { hasText: supplierName });
    await expect(row).toBeVisible();

    // No balance yet - no invoices or payments recorded.
    await row.getByRole("button", { name: "View" }).click();
    await expect(page.getByText(`${supplierName} — invoices, payments & statement`)).toBeVisible();

    // --- Record an invoice (money owed to the supplier) ---
    await page.getByRole("button", { name: "Record invoice" }).click();
    await page.getByRole("dialog").getByLabel("Amount (PKR)").fill("50000");
    await page.getByRole("dialog").getByLabel("Invoice date").fill(new Date().toISOString().slice(0, 10));
    await page.getByRole("dialog").getByLabel("Reference").fill("INV-E2E-001");
    await page.getByRole("dialog").getByRole("button", { name: "Record invoice" }).click();
    await expect(page.getByText("Invoice recorded.")).toBeVisible();
    await expect(page.getByText("Total invoiced: PKR 50,000.00")).toBeVisible();

    // Balance now reflects the invoice.
    await expect(page.getByText("PKR 50,000.00").first()).toBeVisible();

    // --- Record a payment - must NOT reduce the balance until approved ---
    await page.getByRole("tab", { name: "Payments" }).click();
    await page.getByRole("button", { name: "Record payment" }).click();
    await page.getByRole("dialog").getByLabel("Amount (PKR)").fill("20000");
    await page.getByRole("dialog").getByLabel("Payment date").fill(new Date().toISOString().slice(0, 10));
    await page.getByRole("dialog").getByRole("button", { name: "Record payment" }).click();
    await expect(page.getByText("Payment recorded — awaiting approval before it counts against the balance.")).toBeVisible();

    const paymentRow = page.locator("table tbody tr", { hasText: "20,000.00" });
    await expect(paymentRow.getByText("pending", { exact: true })).toBeVisible();

    // Balance is still 50,000 - the pending payment hasn't counted yet.
    await expect(page.getByText("PKR 50,000.00").first()).toBeVisible();

    // --- Approve the payment - balance should now drop to 30,000 ---
    await paymentRow.getByRole("button", { name: "Approve" }).click();
    await page.getByRole("button", { name: "Yes, approve" }).click();
    await expect(page.getByText("Payment approved.")).toBeVisible();
    await expect(paymentRow.getByText("approved", { exact: true })).toBeVisible();
    await expect(page.getByText("PKR 30,000.00").first()).toBeVisible();

    // --- Statement reflects both entries with a correct running balance ---
    await page.getByRole("tab", { name: "Statement" }).click();
    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.getByText("INV-E2E-001")).toBeVisible();
    await expect(page.getByText("PKR 30,000.00").first()).toBeVisible();

    // --- The Balances tab (cross-supplier financial summary) shows it too ---
    await page.getByRole("tab", { name: "Balances", exact: true }).click();
    const balanceRow = page.locator("table tbody tr", { hasText: supplierName });
    await expect(balanceRow.getByText("PKR 30,000.00")).toBeVisible();
  });

  test("Cashier (no supplier:read) sees Access restricted on the Suppliers page", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/suppliers`);
    await expect(page.getByText("Access restricted")).toBeVisible();
  });

  test("Accountant can read and record but has no Add supplier control (no supplier:manage)", async ({ page }) => {
    await loginAs(page, state.roles.accountant.email, state.roles.accountant.password);
    await page.goto(`/dashboard/org/${state.orgId}/suppliers`);
    await expect(page.getByRole("heading", { name: "Suppliers" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add supplier" })).toHaveCount(0);
  });
});
