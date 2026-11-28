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

/** A node's card: the group its id names, which says a queued change in data-change. */
function card(page: Page, id: string) {
  return node(page, id).getByRole("group", { name: id, exact: true });
}

/** The queued changes' rows (patchbay's ChangeList, a region named "Queued changes"). */
function queued(page: Page) {
  return page.getByRole("region", { name: "Queued changes" }).getByRole("listitem");
}

/** The add-node palette's option for a node type or another name of one, by its label. */
function typeOption(page: Page, label: string) {
  return page.getByRole("option").filter({ has: page.getByText(label, { exact: true }) });
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
  const palette = page.getByRole("dialog", { name: "Add a node" });
  await palette.getByRole("combobox", { name: "Add a node" }).fill("console");
  const option = typeOption(page, "ConsoleSink");
  await expect(option).toContainText("Sink node that logs frame data to the console.");
  await option.click();
  await expect(palette).toHaveCount(0);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toHaveAccessibleName("New ConsoleSink");
  await dialog.getByLabel("fps", { exact: true }).fill("1");
  await expect(dialog.getByRole("status")).toContainText("in: dmx");
  await dialog.getByRole("button", { name: "Queue" }).click();
  await expect(dialog).toHaveCount(0);
  await settle(page);

  await node(page, "rgb")
    .locator(".react-flow__handle.source")
    .dragTo(node(page, "console_sink_1").locator(".react-flow__handle.target"));
  await expect(queued(page)).toHaveCount(2);
  // The queued connection is drawn as patchbay's Wire in the added tone, dashed until saved
  const wire = page.getByRole("group", { name: "Edge from rgb to console_sink_1" }).locator("[data-tone]");
  await expect(wire).toHaveAttribute("data-tone", "added");
  await expect(wire).toHaveAttribute("data-dashed", "");
  const diff = page.getByRole("region", { name: "What Save writes" });
  await expect(diff.getByRole("button", { name: "rasl.conf" })).toHaveAttribute("aria-expanded", "true");
  await expect(diff).toContainText("+    node ConsoleSink console_sink_1 {");
  // A file's section folds from its heading, and opens again
  await diff.getByRole("button", { name: "rasl.conf" }).click();
  await expect(diff.getByText("+    node ConsoleSink console_sink_1 {")).toBeHidden();
  await diff.getByRole("button", { name: "rasl.conf" }).click();
  await expect(diff.getByText("+    node ConsoleSink console_sink_1 {")).toBeVisible();
  await expect(card(page, "console_sink_1")).toHaveAttribute("data-change", "added");

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
  await expect(node(page, "console").locator('.react-flow__handle[data-hint="ok"]')).toHaveCount(1);
  await expect(node(page, "rgb").locator('.react-flow__handle[data-hint="no"]')).toHaveCount(1);
  // Over the refusing port, the canvas's status line says why; dropped there, that it was not connected
  const own = await node(page, "rgb").locator(".react-flow__handle.target").boundingBox();
  if (!own) throw new Error("no handle");
  await page.mouse.move(own.x + own.width / 2, own.y + own.height / 2, { steps: 5 });
  const status = page.getByRole("status").filter({ hasText: "wired to itself" });
  await expect(status).toHaveText("A node is not wired to itself");
  await page.mouse.up();
  await expect(page.locator(".react-flow__handle[data-hint]")).toHaveCount(0);
  await expect(status).toHaveText("Not connected: A node is not wired to itself");
  await expect(queued(page)).toHaveCount(0);
});

test("a port is wired from the keyboard by its Connect to choice in the inspector", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: /Add node/ }).click();
  await page.getByRole("dialog", { name: "Add a node" }).getByRole("combobox", { name: "Add a node" }).fill("console");
  await typeOption(page, "ConsoleSink").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("fps", { exact: true }).fill("1");
  await dialog.getByRole("button", { name: "Queue" }).click();
  await settle(page);

  // The new node is selected: its input lists the outputs that take it, by the canvas's own rule, and no input
  const choice = page.getByRole("combobox", { name: "Connect input dmx to" });
  const handle = await node(page, "rgb").locator(".react-flow__handle.source").getAttribute("data-handleid");
  const output = `rgb.${(handle ?? "").replace(/^out:/, "")}`;
  await expect(choice.getByRole("option", { name: output, exact: true })).toHaveCount(1);
  await expect(choice.getByRole("option", { name: "console.dmx", exact: true })).toHaveCount(0);
  await choice.selectOption({ label: output });
  await expect(queued(page)).toHaveCount(2);
  await expect(queued(page).nth(1)).toContainText(`rgb → console_sink_1`);
  await expect(choice).toHaveValue("");
  const wire = page.getByRole("group", { name: "Edge from rgb to console_sink_1" }).locator("[data-tone]");
  await expect(wire).toHaveAttribute("data-tone", "added");
  await expect(wire).toHaveAttribute("data-dashed", "");
});

/**
 * Press a port's handle and move off it, then say whether a wire drag began: its line is drawn, or the ports are
 * marked for it (React Flow draws no line while the graph is not connectable, but a drag that began still marks
 * them). The pointer goes back before it is let go, so a press that pans the view instead leaves it where it was.
 */
async function dragsWire(page: Page, handle: ReturnType<Page["locator"]>): Promise<boolean> {
  const box = await handle.boundingBox();
  if (!box) throw new Error("no handle");
  const from = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 60, from.y + 40, { steps: 6 });
  const drawn =
    (await page.locator(".react-flow__connectionline").count()) > 0 ||
    (await page.locator(".react-flow__handle[data-hint]").count()) > 0;
  await page.mouse.move(from.x, from.y, { steps: 6 });
  await page.mouse.up();
  return drawn;
}

test("ports on a node queued for removal, and every port of a read-only graph, start no wire", async ({ page }) => {
  await open(page);
  const palette = page.getByRole("dialog", { name: "Add a node" });
  // A port of a node that stays starts a wire (dropped on empty canvas from an input, it adds nothing)
  expect(await dragsWire(page, node(page, "console").locator(".react-flow__handle.target"))).toBe(true);
  await expect(palette).toHaveCount(0);

  await node(page, "console").click();
  await page.keyboard.press("Delete");
  await expect(card(page, "console")).toHaveAttribute("data-change", "removed");
  expect(await dragsWire(page, node(page, "console").locator(".react-flow__handle.target"))).toBe(false);
  await expect(palette).toHaveCount(0);
  await expect(queued(page)).toHaveCount(1);

  // A graph the server cannot save (editable false) starts no wire from any port
  await page.route("**/graphql", async (route) => {
    const body = route.request().postData() ?? "";
    if (!body.includes("configGraph")) return route.continue();
    const response = await route.fetch();
    const json = (await response.json()) as { data: { configGraph: { editable: boolean } | null } };
    if (json.data.configGraph) json.data.configGraph.editable = false;
    return route.fulfill({ response, json });
  });
  await open(page);
  await expect(page.getByRole("button", { name: /^Add node/ })).toHaveCount(0);
  const handles = page.locator(".react-flow__handle");
  await expect(handles).toHaveCount(11);
  for (let i = 0; i < 11; i++) expect(await dragsWire(page, handles.nth(i)), `port ${i}`).toBe(false);
  await expect(palette).toHaveCount(0);
});

test("a connection the graph refuses names its ports and cannot be saved", async ({ page }) => {
  await open(page);
  await node(page, "hue")
    .locator(".react-flow__handle.source")
    .dragTo(node(page, "console").locator(".react-flow__handle.target"));
  await expect(page.locator('[data-outcome="error"]')).toContainText("Overlapping connections into console.dmx");
  // The two ports it names carry a warning mark with its words: hue's output and console's input
  const problem = /Overlapping connections into console\.dmx/;
  await expect(page.locator(".react-flow__node").getByText(problem)).toHaveCount(2);
  await expect(node(page, "hue").getByText(problem)).toHaveCount(1);
  await expect(node(page, "console").getByText(problem)).toHaveCount(1);
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

test("the queue keeps the net change: a rename back drops the rename, and each row can be dropped", async ({
  page,
}) => {
  await open(page);
  await node(page, "console").click();
  const id = page.getByLabel("id", { exact: true });
  await id.fill("console2");
  await page.getByRole("button", { name: "Rename" }).click();
  await expect(queued(page)).toHaveCount(1);
  await expect(queued(page).first()).toContainText("renamed");
  await expect(queued(page).first()).toContainText("console → console2");
  await expect(card(page, "console2")).toHaveAttribute("data-change", "renamed");
  // Renamed back to the name the file gives it, the node has no change left
  await node(page, "console2").click();
  await id.fill("console");
  await page.getByRole("button", { name: "Rename" }).click();
  await expect(queued(page)).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Queued changes" }).getByRole("status")).toHaveText(
    "No changes queued",
  );
  await expect(card(page, "console")).not.toHaveAttribute("data-change");

  await node(page, "console").click();
  await page.keyboard.press("Delete");
  await expect(queued(page)).toHaveCount(1);
  await expect(queued(page).first()).toContainText("removed");
  await queued(page).first().getByRole("button", { name: "Drop" }).click();
  await expect(queued(page)).toHaveCount(0);
  await expect(card(page, "console")).not.toHaveAttribute("data-change");
});

test("removing a node removes its connections, and the running graph drops it", async ({ page }) => {
  await open(page);
  await node(page, "console").click();
  await page.keyboard.press("Delete");
  await expect(card(page, "console")).toHaveAttribute("data-change", "removed");
  await save(page);
  expect(readFileSync(CONFIG, "utf8")).not.toContain("node ConsoleSink console");
  await expect.poll(() => runningNodes(page)).not.toContain("console");
});

test("the side panel is resized from its splitter, hidden from the top bar, and both are kept", async ({ page }) => {
  await open(page);
  const side = page.getByRole("complementary", { name: "Side panel" });
  const before = (await side.boundingBox())?.width ?? 0;
  const splitter = page.getByRole("separator", { name: "Resize the side panel" });
  await splitter.focus();
  // On the panel's left edge, the left arrow widens it
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await side.boundingBox())?.width ?? 0).toBeGreaterThan(before + 20);
  await page.keyboard.press("Home");
  await expect(splitter).toHaveAttribute("aria-valuenow", "280");
  // Its width is kept across a reload
  await page.reload();
  await expect(splitter).toHaveAttribute("aria-valuenow", "280");

  // The top bar's button hides it, which is kept too; a selection shows it again
  const toggle = page.getByRole("button", { name: "Side panel" });
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await toggle.click();
  await expect(side).toHaveCount(0);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.reload();
  await expect(page.locator(".react-flow__node")).toHaveCount(5);
  await expect(side).toHaveCount(0);
  await node(page, "console").click();
  await expect(side.getByRole("heading", { name: "ConsoleSink" })).toBeVisible();
  await expect(splitter).toHaveAttribute("aria-valuenow", "280");
});

test("a double-click on empty canvas, or a wire dropped there, opens the palette at that point", async ({ page }) => {
  await open(page);
  const pane = await page.locator(".react-flow__pane").boundingBox();
  if (!pane) throw new Error("no pane");
  // Near the canvas's top-left corner: inside the fit's padding, so empty canvas
  const at = { x: pane.x + 30, y: pane.y + 30 };
  const palette = page.getByRole("dialog", { name: "Add a node" });
  await page.mouse.dblclick(at.x, at.y);
  await expect(palette).toBeVisible();
  const placed = await palette.boundingBox();
  expect(placed && [Math.round(placed.x), Math.round(placed.y)]).toEqual([Math.round(at.x), Math.round(at.y)]);
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);

  // A wire from rgb's output dropped there: the new node is fed by it
  const handle = await node(page, "rgb").locator(".react-flow__handle.source").boundingBox();
  if (!handle) throw new Error("no handle");
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.mouse.down();
  await page.mouse.move(at.x, at.y, { steps: 8 });
  await page.mouse.up();
  await expect(palette).toBeVisible();
  const dropped = await palette.boundingBox();
  expect(dropped && [Math.round(dropped.x), Math.round(dropped.y)]).toEqual([Math.round(at.x), Math.round(at.y)]);
  await palette.getByRole("combobox", { name: "Add a node" }).fill("console");
  await typeOption(page, "ConsoleSink").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toHaveAccessibleName(/^New ConsoleSink fed by rgb\./);
  await dialog.getByLabel("fps", { exact: true }).fill("1");
  await dialog.getByRole("button", { name: "Queue" }).click();
  await expect(queued(page)).toHaveCount(2);
  await settle(page);
  await expect(card(page, "console_sink_1")).toHaveAttribute("data-change", "added");
  // The canvas's tools are patchbay's: once the view is panned away, their fit tool brings the whole graph back
  const tools = page.getByRole("toolbar", { name: "Canvas" });
  const fit = tools.getByRole("button", { name: "Fit the view" });
  const viewport = page.locator(".react-flow__viewport");
  await fit.click();
  await settle(page);
  const fitted = await viewport.getAttribute("style");
  await page.mouse.move(at.x, at.y);
  await page.mouse.down();
  await page.mouse.move(at.x + 150, at.y + 100, { steps: 8 });
  await page.mouse.up();
  await settle(page);
  expect(await viewport.getAttribute("style")).not.toBe(fitted);
  await fit.click();
  await settle(page);
  expect(await viewport.getAttribute("style")).toBe(fitted);
});

test("a zoom from the canvas tools stops the view following, until the fit tool", async ({ page }) => {
  await open(page);
  const viewport = page.locator(".react-flow__viewport");
  const tools = page.getByRole("toolbar", { name: "Canvas" });
  await tools.getByRole("button", { name: "Zoom out" }).click();
  await settle(page);
  const zoomed = await viewport.getAttribute("style");
  await page.getByRole("button", { name: /Add node/ }).click();
  await page.getByRole("dialog", { name: "Add a node" }).getByRole("combobox", { name: "Add a node" }).fill("console");
  await typeOption(page, "ConsoleSink").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("fps", { exact: true }).fill("1");
  await dialog.getByRole("button", { name: "Queue" }).click();
  await expect(card(page, "console_sink_1")).toHaveAttribute("data-change", "added");
  await settle(page);
  // The new layout was not fitted: the view stays where the zoom left it
  expect(await viewport.getAttribute("style")).toBe(zoomed);
  await tools.getByRole("button", { name: "Fit the view" }).click();
  await settle(page);
  expect(await viewport.getAttribute("style")).not.toBe(zoomed);
});

test("an empty graph says so on the canvas, with the add gestures only while it can be edited", async ({ page }) => {
  let editable = true;
  await page.route("**/graphql", async (route) => {
    const body = route.request().postData() ?? "";
    if (!body.includes("configGraph")) return route.continue();
    const response = await route.fetch();
    const json = (await response.json()) as {
      data: { configGraph: { editable: boolean; nodes: unknown[]; edges: unknown[] } | null };
    };
    if (json.data.configGraph) Object.assign(json.data.configGraph, { nodes: [], edges: [], editable });
    return route.fulfill({ response, json });
  });
  await page.goto("/");
  const hint = page.getByText("The config has no nodes yet.");
  await expect(hint).toBeVisible();
  await expect(page.getByText(/^Double-click to add a node, or press /)).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(0);

  editable = false;
  await page.reload();
  await expect(hint).toBeVisible();
  await expect(page.getByText(/^Double-click to add a node/)).toHaveCount(0);
});

test("a click on empty canvas keeps the view following: the next layout is fitted", async ({ page }) => {
  await open(page);
  const viewport = page.locator(".react-flow__viewport");
  const before = await viewport.getAttribute("style");
  // A click that deselects does not move the view, so the view still follows the layout
  await page.locator(".react-flow__pane").click({ position: { x: 10, y: 10 } });
  await page.getByRole("button", { name: /Add node/ }).click();
  await page.getByRole("dialog", { name: "Add a node" }).getByRole("combobox", { name: "Add a node" }).fill("console");
  await typeOption(page, "ConsoleSink").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("fps", { exact: true }).fill("1");
  await dialog.getByRole("button", { name: "Queue" }).click();
  await expect(card(page, "console_sink_1")).toHaveAttribute("data-change", "added");
  await settle(page);
  // The new layout was fitted: the view moved, and the fit tool leaves it where it is
  const followed = await viewport.getAttribute("style");
  expect(followed).not.toBe(before);
  await page.getByRole("toolbar", { name: "Canvas" }).getByRole("button", { name: "Fit the view" }).click();
  await settle(page);
  expect(await viewport.getAttribute("style")).toBe(followed);
});

test("adding a node: the palette and the dialog close on Escape and give focus back", async ({ page }) => {
  await open(page);
  const opener = page.getByRole("button", { name: /Add node/ });
  await opener.click();
  const palette = page.getByRole("dialog", { name: "Add a node" });
  const search = palette.getByRole("combobox", { name: "Add a node" });
  await expect(search).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
  await expect(opener).toBeFocused();

  // A type is found by another name it is registered under; Enter picks the first match
  await opener.click();
  await search.fill("consolesinknode");
  await expect(page.getByRole("option")).toHaveCount(1);
  await expect(typeOption(page, "ConsoleSinkNode")).toContainText("Another name for ConsoleSink");
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toHaveAccessibleName("New ConsoleSink");
  await dialog.getByRole("button", { name: "Back" }).click();
  await expect(search).toBeFocused();
  await expect(search).toHaveValue("");
  await search.fill("console");
  await typeOption(page, "ConsoleSink").click();
  await expect(dialog).toHaveAccessibleName("New ConsoleSink");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();

  await opener.click();
  await typeOption(page, "ConsoleSink").click();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  await expect(queued(page)).toHaveCount(0);
});

test("the editor's keys: Mod+Z drops the last change, a text field keeps Delete and the single keys", async ({
  page,
}) => {
  await open(page);
  // Delete in the rename field edits the text; the node stays
  await node(page, "console").click();
  const rename = page.getByLabel("id", { exact: true });
  await rename.focus();
  await page.keyboard.press("Delete");
  await expect(queued(page)).toHaveCount(0);
  // A, F and ? type into the field: no palette, no sheet; Mod+K still opens the palette there
  await rename.fill("");
  await page.keyboard.type("af?");
  await expect(rename).toHaveValue("af?");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog", { name: "Commands" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await node(page, "console").click();
  await page.keyboard.press("Delete");
  await expect(queued(page)).toHaveCount(1);
  await page.keyboard.press("ControlOrMeta+z");
  await expect(queued(page)).toHaveCount(0);
});

test("Mod+K opens the whole palette, adding a node its first group, and its commands run", async ({ page }) => {
  await open(page);
  await page.keyboard.press("ControlOrMeta+k");
  const palette = page.getByRole("dialog", { name: "Commands" });
  const search = palette.getByRole("combobox", { name: "Commands" });
  await expect(search).toBeFocused();
  const groups = palette.getByRole("group");
  await expect(groups.first()).toHaveAccessibleName("Add a node");
  await expect(groups).toHaveText([/^Add a node/, /^Changes/, /^View/, /^Help/]);
  // With nothing queued, the changes cannot act: listed, but disabled
  const option = (name: string) => palette.getByRole("option", { name: new RegExp(`^${name}`) });
  await expect(option("Save the changes")).toHaveAttribute("aria-disabled", "true");
  await expect(option("Fit the view")).toHaveAttribute("aria-keyshortcuts", /F/);

  // A type picked there goes on to the add-node dialog, and Back returns to the whole palette
  await search.fill("console");
  await expect(groups.first()).toHaveAccessibleName("Add a node");
  await typeOption(page, "ConsoleSink").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toHaveAccessibleName("New ConsoleSink");
  await dialog.getByRole("button", { name: "Back" }).click();
  await expect(search).toBeFocused();
  await typeOption(page, "ConsoleSink").click();
  await dialog.getByLabel("fps", { exact: true }).fill("1");
  await dialog.getByRole("button", { name: "Queue" }).click();
  await expect(queued(page)).toHaveCount(1);

  // Now the queue can be discarded from the palette
  await page.keyboard.press("ControlOrMeta+k");
  await expect(option("Discard the changes")).not.toHaveAttribute("aria-disabled", "true");
  await search.fill("discard");
  await page.keyboard.press("Enter");
  await expect(palette).toHaveCount(0);
  await expect(queued(page)).toHaveCount(0);

  // The side panel and the theme are there too
  const side = page.getByRole("button", { name: "Side panel", exact: true });
  await expect(side).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("ControlOrMeta+k");
  await option("Hide the side panel").click();
  await expect(side).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("ControlOrMeta+k");
  await option("Dark theme").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.keyboard.press("ControlOrMeta+k");
  await option("Keyboard shortcuts").click();
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
});

test("A opens adding, F fits the view, and ? lists the keys", async ({ page }) => {
  await open(page);
  await page.keyboard.press("a");
  const adding = page.getByRole("dialog", { name: "Add a node" });
  await expect(adding.getByRole("combobox", { name: "Add a node" })).toBeFocused();
  await expect(adding.getByRole("group").first()).toHaveAccessibleName("Node types");
  await page.keyboard.press("Escape");
  await expect(adding).toHaveCount(0);

  // F fits the view as the fit tool does, and the view follows again
  const viewport = page.locator(".react-flow__viewport");
  const fitted = await viewport.getAttribute("style");
  const tools = page.getByRole("toolbar", { name: "Canvas" });
  await expect(tools.getByRole("button", { name: "Fit the view" })).toHaveAttribute("aria-keyshortcuts", "F");
  await tools.getByRole("button", { name: "Zoom out" }).click();
  await settle(page);
  expect(await viewport.getAttribute("style")).not.toBe(fitted);
  await page.locator(".react-flow__pane").click({ position: { x: 10, y: 10 } });
  await page.keyboard.press("f");
  await settle(page);
  expect(await viewport.getAttribute("style")).toBe(fitted);

  await page.keyboard.press("?");
  const sheet = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(sheet).toBeVisible();
  for (const label of [
    "Open the command palette",
    "Show the keyboard shortcuts",
    "Add a node",
    "Remove the selection",
    "Drop the last change",
    "Fit the view",
  ])
    await expect(sheet.getByRole("term").filter({ hasText: label })).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});

test("a read-only graph: A adds nothing, and the palette and the sheet offer no adding or changes", async ({
  page,
}) => {
  await page.route("**/graphql", async (route) => {
    const body = route.request().postData() ?? "";
    if (!body.includes("configGraph")) return route.continue();
    const response = await route.fetch();
    const json = (await response.json()) as { data: { configGraph: { editable: boolean } | null } };
    if (json.data.configGraph) json.data.configGraph.editable = false;
    return route.fulfill({ response, json });
  });
  await open(page);
  await page.keyboard.press("a");
  await page.keyboard.press("ControlOrMeta+k");
  const palette = page.getByRole("dialog", { name: "Commands" });
  await expect(palette).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Add a node" })).toHaveCount(0);
  await expect(palette.getByRole("group")).toHaveText([/^View/, /^Help/]);
  await page.keyboard.press("Escape");
  await page.keyboard.press("?");
  const sheet = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(sheet.getByRole("term")).toHaveText([
    "Open the command palette",
    "Show the keyboard shortcuts",
    "Fit the view",
  ]);
});

test("the theme switch cycles system, light and dark, and the choice is kept across a reload", async ({ page }) => {
  await open(page);
  const html = page.locator("html");
  const theme = page.getByRole("button", { name: /^Theme:/ });
  await expect(theme).toHaveAccessibleName("Theme: system");
  await expect(html).not.toHaveAttribute("data-theme");
  await theme.click();
  await expect(theme).toHaveAccessibleName("Theme: light");
  await expect(html).toHaveAttribute("data-theme", "light");
  await theme.click();
  await expect(theme).toHaveAccessibleName("Theme: dark");
  await expect(html).toHaveAttribute("data-theme", "dark");

  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(theme).toHaveAccessibleName("Theme: dark");
  await theme.click();
  await expect(html).not.toHaveAttribute("data-theme");
});

test("in a narrow window the side panel is a sheet that a selection opens, from the bottom on a phone", async ({
  page,
}) => {
  await page.setViewportSize({ width: 700, height: 800 });
  await open(page);
  await expect(page.getByRole("complementary", { name: "Side panel" })).toHaveCount(0);
  // The sheet is named by its title, the selection's (the node's type), or "Side panel" with nothing selected
  const sheet = page.getByRole("dialog", { name: "ConsoleSink" });
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await node(page, "console").click();
  await expect(sheet).toBeVisible();
  await expect(sheet).toHaveAttribute("data-side", "end");
  // One header row: the title beside the Close button, and no other heading at its level
  await expect(sheet.getByRole("heading", { level: 2 })).toHaveText(["ConsoleSink"]);
  await expect(sheet.getByRole("heading", { name: "ConsoleSink" })).toBeVisible();
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(sheet).toHaveCount(0);

  const toggle = page.getByRole("button", { name: "Side panel" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(sheet).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await sheet.getByLabel("id", { exact: true }).focus();
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);

  // With nothing selected the top bar's button opens it under the column's own name
  await page.locator(".react-flow__pane").click({ position: { x: 10, y: 10 } });
  await toggle.click();
  const empty = page.getByRole("dialog", { name: "Side panel" });
  await expect(empty.getByRole("heading", { level: 2 })).toHaveText(["Side panel"]);
  await empty.getByRole("button", { name: "Close" }).click();
  await expect(empty).toHaveCount(0);

  await page.setViewportSize({ width: 500, height: 800 });
  await node(page, "console").click();
  await expect(sheet).toHaveAttribute("data-side", "bottom");
  // A press on the canvas closes it
  await page.locator(".react-flow__pane").click({ position: { x: 10, y: 10 } });
  await expect(sheet).toHaveCount(0);
});
