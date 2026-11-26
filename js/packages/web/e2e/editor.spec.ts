// The graph editor end to end: edits made in the page are written to the config file, and
// the running graph reloads them.
import { readFileSync, writeFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { CONFIG } from "../playwright.config";

const FIXTURE = readFileSync("e2e/fixture.conf", "utf8");

/** The ids of the nodes the running graph has now (GraphQL `graph`). */
async function runningNodes(page: Page): Promise<string[]> {
  const response = await page.request.post("/graphql", { data: { query: "{ graph { nodes { id } } }" } });
  const body = (await response.json()) as { data: { graph: { nodes: { id: string }[] } } };
  return body.data.graph.nodes.map((n) => n.id);
}

/**
 * Wait until the page has laid out and fitted the graph it now shows (the canvas's
 * data-layout), and the view has stopped moving.
 */
async function settle(page: Page): Promise<void> {
  await expect(page.locator(".canvas")).toHaveAttribute("data-layout", "ready");
  const viewport = page.locator(".react-flow__viewport");
  let last = "";
  await expect
    .poll(
      async () => {
        const now = (await viewport.getAttribute("style")) ?? "";
        const still = now === last;
        last = now;
        return still;
      },
      { intervals: [300] },
    )
    .toBe(true);
}

async function open(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator(".react-flow__node")).toHaveCount(5);
  await expect(page.getByText("live", { exact: true })).toBeVisible();
  await settle(page);
}

function node(page: Page, id: string) {
  return page.locator(`.react-flow__node[data-id="${id}"]`);
}

async function save(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved rasl.conf" })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  if (readFileSync(CONFIG, "utf8") !== FIXTURE) {
    writeFileSync(CONFIG, FIXTURE);
    // The watcher reloads the restored file before the next test looks at the graph
    await expect
      .poll(async () => (await runningNodes(page)).sort(), { timeout: 10_000 })
      .toEqual(["console", "hsl", "hue", "probe", "rgb"]);
  }
});

test("a node added and wired in the page is saved to the file and runs", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: /Add node/ }).click();
  await page.getByPlaceholder("Search node types").fill("console");
  await page.locator(".type-item", { hasText: "ConsoleSink" }).click();
  await page.locator(".field", { hasText: "fps" }).locator("input").fill("1");
  await expect(page.locator(".preview")).toContainText("in: dmx");
  await page.locator(".dialog").getByRole("button", { name: "Queue" }).click();
  await settle(page);

  await node(page, "rgb")
    .locator(".react-flow__handle.source")
    .dragTo(node(page, "console_sink_1").locator(".react-flow__handle.target"));
  await expect(page.getByRole("list", { name: "Queued changes" }).getByRole("listitem")).toHaveCount(2);
  await expect(page.locator(".diff")).toContainText("+    node ConsoleSink console_sink_1 {");
  await expect(node(page, "console_sink_1").locator(".node-card")).toHaveClass(/status-added/);

  await save(page);
  const text = readFileSync(CONFIG, "utf8");
  expect(text).toContain("    node ConsoleSink console_sink_1 {\n        fps 1;\n        connect rgb;\n    }");
  expect(text).toContain("# a slow rainbow");
  await expect.poll(() => runningNodes(page)).toContain("console_sink_1");
});

test("while a wire is dragged, ports that cannot take it are marked", async ({ page }) => {
  await open(page);
  const handle = node(page, "rgb").locator(".react-flow__handle.source");
  const box = await handle.boundingBox();
  if (!box) throw new Error("no handle");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + 120, box.y + 80, { steps: 5 });
  // rgb emits a color: the sink's dmx input takes it; rgb's own input is marked as not a
  // place to drop it
  await expect(node(page, "console").locator(".react-flow__handle.hint-ok")).toHaveCount(1);
  await expect(node(page, "rgb").locator(".react-flow__handle.hint-no")).toHaveCount(1);
  await page.mouse.up();
  await expect(page.locator(".hint-ok, .hint-no")).toHaveCount(0);
});

test("a connection the graph refuses names its ports and cannot be saved", async ({ page }) => {
  await open(page);
  await node(page, "hue")
    .locator(".react-flow__handle.source")
    .dragTo(node(page, "console").locator(".react-flow__handle.target"));
  await expect(page.locator('[data-outcome="error"]')).toContainText("Overlapping connections into console.dmx");
  await expect(page.locator(".handle-problem")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(readFileSync(CONFIG, "utf8")).toBe(FIXTURE);
});

test("a setting that reads a $variable is changed at its definition or only on its line", async ({ page }) => {
  await open(page);
  await node(page, "hue").click();
  const fps = page.getByRole("group", { name: "fps", exact: true });
  await expect(fps).toContainText("$rate (2 uses)");
  await fps.getByLabel("fps", { exact: true }).fill("4");
  await fps.getByRole("button", { name: "Set" }).click();
  await save(page);
  let text = readFileSync(CONFIG, "utf8");
  expect(text).toContain("@set $rate 4;");
  expect(text.match(/fps \$rate;/g)).toHaveLength(2);

  await node(page, "console").click();
  const line = page.getByRole("group", { name: "fps", exact: true });
  await line.getByLabel("only here").check();
  await line.getByLabel("fps", { exact: true }).fill("1");
  await line.getByRole("button", { name: "Set" }).click();
  await save(page);
  text = readFileSync(CONFIG, "utf8");
  expect(text).toContain("@set $rate 4;");
  expect(text.match(/fps \$rate;/g)).toHaveLength(1);
});

test("a node made by @use takes its argument, and detaches into its own lines", async ({ page }) => {
  await open(page);
  await node(page, "probe").click();
  await expect(page.getByRole("note")).toContainText("@use tap");
  const fps = page.getByRole("group", { name: "fps", exact: true });
  await expect(fps).toContainText("@use argument $fps");
  await fps.getByLabel("fps", { exact: true }).fill("3");
  await fps.getByRole("button", { name: "Set" }).click();
  await save(page);
  expect(readFileSync(CONFIG, "utf8")).toContain("    @use tap probe 3;");

  await node(page, "probe").click();
  await page.getByRole("button", { name: "Detach" }).click();
  await save(page);
  const text = readFileSync(CONFIG, "utf8");
  expect(text).not.toContain("@use tap probe");
  expect(text).toContain(
    "    node ConsoleSink probe {\n        fps 3;\n        max_channels 3;\n        connect rgb;\n    }",
  );
});

test("removing a node removes its connections, and the running graph drops it", async ({ page }) => {
  await open(page);
  await node(page, "console").click();
  await page.keyboard.press("Delete");
  await expect(node(page, "console").locator(".node-card")).toHaveClass(/status-removed/);
  await save(page);
  expect(readFileSync(CONFIG, "utf8")).not.toContain("node ConsoleSink console");
  await expect.poll(() => runningNodes(page)).not.toContain("console");
});

test("the side panel is resized from its splitter", async ({ page }) => {
  await open(page);
  const side = page.locator("aside.side");
  const before = (await side.boundingBox())?.width ?? 0;
  const splitter = page.getByRole("separator", { name: "Resize the side panel" });
  await splitter.focus();
  // On the panel's left edge, the left arrow widens it
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await side.boundingBox())?.width ?? 0).toBeGreaterThan(before + 20);
  await page.keyboard.press("Home");
  await expect(splitter).toHaveAttribute("aria-valuenow", "280");
});
