import { expect, seedSession, settle, test, type Role } from "../harness";

const homes: Array<[Role, string, string, string]> = [
  ["SHIPPING_COMPANY", "/company/overview", "Fleet", "Scenarios"],
  ["PORT_AUTHORITY", "/port/overview", "Arrivals", "Twin"],
  ["VESSEL_OPERATOR", "/vessel/overview", "Traffic", "Scenarios"],
  ["NATIONAL_ADMIN", "/admin/radar", "Ports", "Scenarios"],
];

for (const [role, path, list, workbench] of homes) {
  test(`${role} groups its tools in one right panel`, async ({ context, page }) => {
    await seedSession(context, role);
    await page.goto(path);
    await settle(page);

    const rail = page.getByTestId("workspace-right-panel");
    await expect(rail).toHaveCount(1);
    await expect(rail.getByRole("tablist")).toHaveCount(1);
    await expect(rail.getByRole("tab")).toHaveText(["Now", list, workbench]);
    const now = rail.getByRole("tab", { name: "Now", exact: true });
    await expect(now).toHaveAttribute("aria-selected", "true");
    const dataNow = rail.getByText("Data now", { exact: true });
    await expect(dataNow).toBeVisible();

    for (const name of [list, workbench]) {
      const tab = rail.getByRole("tab", { name, exact: true });
      await tab.click();
      await expect(tab).toHaveAttribute("aria-selected", "true");
      await expect(dataNow).toHaveCount(0);
    }
    await now.click();
    await expect(dataNow).toBeVisible();
  });
}
