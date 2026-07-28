import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  finalizeStyleBatch,
  isManagedRemoteUrl,
  loadOssConfig,
  preflightStyleBatch,
} from "./finalize_style_batch.mjs";

const CONFIG = {
  accessKeyId: "test-ak",
  accessKeySecret: "test-sk",
  bucket: "test-assets",
  endpoint: "oss-cn-shanghai.aliyuncs.com",
  domain: "assets.example.com",
  prefix: "dev/",
};

function templateData(key = "chrome-balloon-sculpture") {
  return {
    schemaVersion: "1.0",
    taxonomyVersion: "2.0",
    key,
    title: "镜面气球雕塑",
    description: "把主体塑造成镜面气球雕塑",
    category: {
      primary: "material-3d",
      secondary: "chrome-inflatable-sculpture",
      displayName: "材质立体",
    },
    displayCategory: "材质立体",
    tags: ["镜面", "气球"],
    styleTags: ["镜面", "气球"],
    referenceType: "paired-images",
    referenceStructure: "paired-images",
    supportedModes: ["subject_only"],
    contentScope: "subject",
    contentStrategy: "primary_subject_reconstruction",
    referenceAssets: { source: "./same.png", style: "./same.png" },
    testAssets: { input: "./test.png", output: "./test.png" },
    testNotes: ["本地测试记录"],
    reviewNotes: ["待复核"],
    styleInstruction: "保持主体身份、数量、姿态和轮廓，将主体重建为圆润的镜面气球雕塑。",
    contentExclusion: "不要复制参考图中的具体主体、文字、品牌和背景故事。",
    classificationConfidence: 0.94,
    needsReview: true,
  };
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "style-finalizer-"));
  const input = path.join(root, "input");
  const output = path.join(root, "handoff", "batch-one");
  const templateDir = path.join(input, "0001");
  await mkdir(templateDir, { recursive: true });
  await writeFile(path.join(templateDir, "same.png"), "same-image");
  await writeFile(path.join(templateDir, "test.png"), "test-image");
  await writeFile(
    path.join(templateDir, "style-template.json"),
    `${JSON.stringify(templateData(), null, 2)}\n`,
  );
  return { root, input, output, templateDir };
}

async function mockValidate(file, mode, config) {
  const data = JSON.parse(await readFile(file, "utf8"));
  if (mode === "remote") {
    for (const value of Object.values(data.referenceAssets)) {
      assert.equal(isManagedRemoteUrl(value, config), true);
    }
    assert.equal("testAssets" in data, false);
    assert.equal("testNotes" in data, false);
    assert.equal("reviewNotes" in data, false);
  }
}

test("validates OSS configuration without exposing secrets", () => {
  assert.throws(() => loadOssConfig({}), /缺少 OSS 环境变量/);
  assert.throws(() => loadOssConfig({
    ALIYUN_OSS_ACCESS_KEY_ID: "ak",
    ALIYUN_OSS_ACCESS_KEY_SECRET: "sk",
    ALIYUN_OSS_ASSETS_BUCKET: "bucket",
    ALIYUN_OSS_ASSETS_ENDPOINT: "https://oss.example.com",
    ALIYUN_OSS_ASSETS_DOMAIN: "assets.example.com",
  }), /纯 hostname/);
});

test("dry-run validates and reports hash duplicates without OSS", async () => {
  const value = await fixture();
  try {
    const summary = await preflightStyleBatch({ input: value.input });
    assert.equal(summary.templates, 1);
    assert.equal(summary.localAssets, 2);
    assert.equal(summary.uniqueLocalAssets, 1);
    assert.equal(summary.duplicateAssets, 1);
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("uploads reference assets once and writes one clean JSON", async () => {
  const value = await fixture();
  try {
    const sourceFile = path.join(value.templateDir, "style-template.json");
    const sourceBefore = await readFile(sourceFile, "utf8");
    const uploads = [];
    const summary = await finalizeStyleBatch({
      input: value.input,
      output: value.output,
      config: CONFIG,
      validateFile: mockValidate,
      uploadObject: async (upload) => { uploads.push(upload); },
    });
    assert.equal(summary.templates, 1);
    assert.equal(summary.uploaded, 1);
    assert.equal(summary.reused, 1);
    assert.equal(uploads.length, 1);
    const finalFile = path.join(value.output, "chrome-balloon-sculpture.json");
    const finalData = JSON.parse(await readFile(finalFile, "utf8"));
    assert.equal(finalData.referenceAssets.source, finalData.referenceAssets.style);
    assert.equal("testAssets" in finalData, false);
    assert.equal(await readFile(sourceFile, "utf8"), sourceBefore);

    const retryUploads = [];
    const retry = await finalizeStyleBatch({
      input: value.input,
      output: value.output,
      config: CONFIG,
      validateFile: mockValidate,
      uploadObject: async (upload) => { retryUploads.push(upload); },
    });
    assert.equal(retryUploads.length, 0);
    assert.equal(retry.uploaded, 0);
    assert.equal(retry.reused, 2);
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("rejects duplicate template keys before uploading", async () => {
  const value = await fixture();
  try {
    const duplicateDir = path.join(value.input, "0002");
    await mkdir(duplicateDir, { recursive: true });
    await writeFile(path.join(duplicateDir, "same.png"), "other-image");
    const duplicate = templateData();
    delete duplicate.testAssets;
    await writeFile(
      path.join(duplicateDir, "style-template.json"),
      `${JSON.stringify(duplicate, null, 2)}\n`,
    );
    let uploads = 0;
    await assert.rejects(
      () => finalizeStyleBatch({
        input: value.input,
        output: value.output,
        config: CONFIG,
        validateFile: mockValidate,
        uploadObject: async () => { uploads += 1; },
      }),
      /key 重复/,
    );
    assert.equal(uploads, 0);
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});
