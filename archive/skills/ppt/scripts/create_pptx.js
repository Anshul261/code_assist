#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const PptxGenJS = require("pptxgenjs");

function argValue(args, name, fallback = undefined) {
  const index = args.indexOf(name);
  if (index === -1 || index + 1 >= args.length) return fallback;
  return args[index + 1];
}

function ensureDir(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function stripMd(text) {
  return String(text || "")
    .replace(/!\[[^\]]*\]\([^)]+\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`>#-]/g, "")
    .trim();
}

function parseImage(line) {
  const match = line.match(/!\[([^\]]*)\]\(([^)]+)\)/);
  if (!match) return null;
  return { alt: match[1], path: match[2] };
}

function parseMarkdown(markdownPath) {
  const root = path.dirname(path.resolve(markdownPath));
  const text = fs.readFileSync(markdownPath, "utf8");
  const lines = text.split(/\r?\n/);
  const titleLine = lines.find((line) => line.startsWith("# "));
  const spec = {
    title: titleLine ? stripMd(titleLine.replace(/^#\s+/, "")) : "Presentation",
    subtitle: "",
    slides: [],
  };
  let current = null;
  for (const line of lines) {
    if (line.startsWith("## ")) {
      if (current) spec.slides.push(current);
      current = { title: stripMd(line.replace(/^##\s+/, "")), bullets: [], images: [] };
      continue;
    }
    if (!current) continue;
    const image = parseImage(line);
    if (image) {
      const imagePath = path.isAbsolute(image.path) ? image.path : path.resolve(root, image.path);
      current.images.push({ ...image, path: imagePath });
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      current.bullets.push(stripMd(line.replace(/^\s*[-*]\s+/, "")));
      continue;
    }
    const cleaned = stripMd(line);
    if (cleaned && current.bullets.length < 5) current.bullets.push(cleaned);
  }
  if (current) spec.slides.push(current);
  if (!spec.slides.length) {
    spec.slides.push({ title: "Summary", bullets: text.split(/\n+/).map(stripMd).filter(Boolean).slice(0, 6), images: [] });
  }
  return spec;
}

function loadSpec(specPath) {
  const resolved = path.resolve(specPath);
  const raw = fs.readFileSync(resolved, "utf8");
  if (resolved.endsWith(".json")) {
    const spec = JSON.parse(raw);
    spec.slides = spec.slides || [];
    return spec;
  }
  return parseMarkdown(resolved);
}

function addTitle(slide, text, opts = {}) {
  slide.addText(text, {
    x: 0.55,
    y: opts.y || 0.35,
    w: 12.2,
    h: opts.h || 0.55,
    fontFace: "Aptos Display",
    fontSize: opts.size || 26,
    bold: true,
    color: "1F2937",
    margin: 0,
    breakLine: false,
    fit: "shrink",
  });
}

function addBullets(slide, bullets, x, y, w, h) {
  const safeBullets = (bullets || []).filter(Boolean).slice(0, 7);
  if (!safeBullets.length) return;
  slide.addText(
    safeBullets.map((text) => ({ text, options: { bullet: { type: "ul" } } })),
    {
      x,
      y,
      w,
      h,
      fontFace: "Aptos",
      fontSize: 15,
      color: "374151",
      breakLine: false,
      fit: "shrink",
      paraSpaceAfterPt: 8,
      valign: "top",
    }
  );
}

function addImageIfPresent(slide, image, x, y, w, h) {
  if (!image || !image.path || !fs.existsSync(image.path)) return false;
  slide.addImage({ path: image.path, x, y, w, h, sizing: { type: "contain", x, y, w, h } });
  return true;
}

async function createDeck(specPath, outputPath) {
  const spec = loadSpec(specPath);
  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "Code Assist";
  pptx.subject = spec.title || "Generated presentation";
  pptx.title = spec.title || "Presentation";
  pptx.company = "Code Assist";
  pptx.lang = "en-US";
  pptx.theme = {
    headFontFace: "Aptos Display",
    bodyFontFace: "Aptos",
    lang: "en-US",
  };

  const cover = pptx.addSlide();
  cover.background = { color: "F8FAFC" };
  cover.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 13.333, h: 0.16, fill: { color: "2563EB" }, line: { color: "2563EB" } });
  cover.addText(spec.title || "Presentation", {
    x: 0.75,
    y: 2.0,
    w: 11.8,
    h: 0.8,
    fontFace: "Aptos Display",
    fontSize: 34,
    bold: true,
    color: "111827",
    fit: "shrink",
  });
  if (spec.subtitle) {
    cover.addText(spec.subtitle, { x: 0.78, y: 2.85, w: 10.8, h: 0.55, fontSize: 17, color: "4B5563", fit: "shrink" });
  }
  cover.addText(new Date().toISOString().slice(0, 10), { x: 0.78, y: 6.7, w: 3, h: 0.25, fontSize: 10, color: "6B7280" });

  for (const item of spec.slides || []) {
    const slide = pptx.addSlide();
    slide.background = { color: "FFFFFF" };
    slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 13.333, h: 0.08, fill: { color: "2563EB" }, line: { color: "2563EB" } });
    addTitle(slide, item.title || "Slide");
    const images = item.images || (item.image ? [{ path: item.image }] : []);
    if (images.length && fs.existsSync(images[0].path)) {
      addBullets(slide, item.bullets, 0.7, 1.25, 5.1, 5.4);
      addImageIfPresent(slide, images[0], 6.05, 1.15, 6.65, 5.45);
    } else {
      addBullets(slide, item.bullets, 0.85, 1.25, 11.6, 5.4);
    }
    if (item.notes) slide.addNotes(String(item.notes));
  }

  ensureDir(outputPath);
  await pptx.writeFile({ fileName: outputPath });
  return { status: "success", output: outputPath, slides: (spec.slides || []).length + 1 };
}

async function main() {
  const args = process.argv.slice(2);
  const spec = argValue(args, "--spec");
  const output = argValue(args, "--output", "output/decks/presentation.pptx");
  if (!spec) {
    console.error(JSON.stringify({ status: "error", error: "Missing --spec path" }));
    process.exit(2);
  }
  try {
    const result = await createDeck(spec, path.resolve(output));
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(JSON.stringify({ status: "error", error: error.message }, null, 2));
    process.exit(1);
  }
}

main();
