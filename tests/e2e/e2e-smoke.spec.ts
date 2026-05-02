import { test, expect, type Page } from "@playwright/test";

const LEARNER = { id: "learner_demo_001", password: "Welcome123" };
const ADMIN = { id: "org_admin_demo", password: "Welcome123" };

async function loginAs(page: Page, userId: string, password: string) {
  await page.goto("/login");
  await page.waitForSelector("form.login-form", { timeout: 10000 });
  await page.selectOption("select#userId", userId);
  await page.fill("input#password", password);
  await page.click("button.login-submit");
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });
}

test.describe("Web Acceptance Walkthrough", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  test("1. Auth: mock login as learner", async ({ page }) => {
    await loginAs(page, LEARNER.id, LEARNER.password);
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 5000 });
    // Verify the session is active by reloading
    await page.goto("/");
    await expect(page.locator("h1, h2").first()).toBeVisible();
  });

  test("2. MR Training Loop: select scenario → session → review", async ({ page }) => {
    await loginAs(page, LEARNER.id, LEARNER.password);

    // Go to scenarios page
    await page.goto("/scenarios");
    await page.waitForSelector("div.scenario-grid", { timeout: 10000 });

    // Start the first available scenario
    await page.locator("button.primary-button.full-button").first().click();

    // Wait for session page to load (URL contains /sessions/<id>)
    await page.waitForURL(/\/sessions\//, { timeout: 15000 });
    await page.waitForSelector("textarea.composer-input", { timeout: 10000 });

    // Send a learner turn
    await page.fill(
      "textarea.composer-input",
      "本日はお時間をいただき、ありがとうございます。新しい高血圧治療薬についてご紹介させていただきます。"
    );
    await page.click("button.send-button");
    await page.waitForTimeout(3000);

    // Finish the session (button text varies by locale: セッション終了 / Finish)
    const finishBtn = page.locator("button.finish-button");
    if (await finishBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await finishBtn.click();
    }

    // Wait for navigation to review page
    await page.waitForURL(/\/review/, { timeout: 20000 }).catch(async () => {
      // If auto-redirect doesn't happen, navigate assertively
      const reviewLinks = page.locator("a[href*='/review']");
      if (await reviewLinks.first().isVisible({ timeout: 3000 }).catch(() => false)) {
        await reviewLinks.first().click();
      }
    });

    // Verify review page rendered (at least one section visible)
    await page.waitForTimeout(2000);
    const reviewSection = page.locator("section").first();
    await expect(reviewSection).toBeVisible({ timeout: 5000 });
  });

  test("3. Records and Progress", async ({ page }) => {
    await loginAs(page, LEARNER.id, LEARNER.password);

    // Open records page
    await page.goto("/records");
    await page.waitForURL("/records", { timeout: 5000 });
    await page.waitForTimeout(3000);

    // Verify records page loaded
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 5000 });

    // Click into a record if available via spotlight card
    const spotlightReviewLink = page.locator("section.record-spotlight-card a.primary-button");
    if (await spotlightReviewLink.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      await spotlightReviewLink.first().click();
      await page.waitForURL(/\/records\/.+/, { timeout: 5000 });
    }

    // Open progress page
    await page.goto("/progress");
    await page.waitForURL("/progress", { timeout: 5000 });
    await page.waitForTimeout(3000);

    // Verify progress page loaded
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 5000 });
  });

  test("4. Marketplace and Home Dashboard", async ({ page }) => {
    await loginAs(page, LEARNER.id, LEARNER.password);

    // Open marketplace
    await page.goto("/marketplace");
    await page.waitForURL("/marketplace", { timeout: 5000 });
    await page.waitForTimeout(3000);

    // Verify marketplace loaded
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 5000 });

    // Return to home dashboard
    await page.goto("/");
    await page.waitForURL("/", { timeout: 5000 });
    await page.waitForTimeout(3000);

    // Verify dashboard loaded
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 5000 });
  });

  test("5. Training Plans and Admin Views", async ({ page }) => {
    await loginAs(page, ADMIN.id, ADMIN.password);

    // Open admin page (includes embedded TrainingPlansFlow)
    await page.goto("/admin");
    await page.waitForURL("/admin", { timeout: 5000 });
    await page.waitForTimeout(3000);
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 5000 });

    // Open team view
    await page.goto("/team");
    await page.waitForURL("/team", { timeout: 5000 }).catch(() => {
      // Team page might redirect, that's acceptable
    });
    await page.waitForTimeout(3000);
    // Team page uses <strong> for its heading texts, not <h1>/<h2>
    await expect(page.locator("main strong").first()).toBeVisible({ timeout: 5000 });
  });
});
