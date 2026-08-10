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

const PROMPT = "以第 2 张图片（用户上传图）作为唯一内容来源，保持主体、数量、身份、姿态、轮廓、物件关系、视角与构图。第 1 张图片仅作为风格参考，把第 2 张图片完整重绘为高反射抛光铬材质，使用连续圆润曲面、宽阔高光、深色反射带和柔和接触阴影塑造体积。严禁复制第 1 张图片中的气球、人物、道具、场景、文字、品牌、边框和装饰；不得新增用户图中不存在的主体或可读文字。原照片像素、写实皮肤、真实毛发、摄影景深、镜头光照、照片噪声和滤镜式处理痕迹必须完全消失，结果必须保持用户上传内容可识别。";

function templateData(key = "high-gloss-chrome-rendering") {
  return {
    key,
    title: "高光镜面塑形",
    description: "以高反射镜面、宽阔高光和圆润块面重绘你的图片",
    kind: "STYLE_REF",
    cover: "./same.png",
    referenceImage: "./same.png",
    imageSize: "1024x1024",
    imageN: 1,
    promptTemplate: PROMPT,
    inputSchema: [{
      type: "image",
      id: "source",
      label: "你的原图",
      hint: "上传一张想要转换风格的图片",
      required: true,
      maxCount: 1,
      private: false,
    }],
    preprocessSteps: [],
    metadata: {
      sourceRef: {
        producerKey: key,
        styleAsset: "风格化素材/0001.png",
        taxonomyVersion: "2.0",
      },
    },
  };
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "style-finalizer-"));
  const input = path.join(root, "input");
  const output = path.join(root, "handoff", "batch-one");
  const templateDir = path.join(input, "0001");
  await mkdir(templateDir, { recursive: true });
  await writeFile(path.join(templateDir, "same.png"), "same-image");
  await writeFile(
    path.join(templateDir, "style-template.json"),
    `${JSON.stringify(templateData(), null, 2)}\n`,
  );
  return { root, input, output, templateDir };
}

async function mockValidate(file, mode, config) {
  const data = JSON.parse(await readFile(file, "utf8"));
  if (mode === "remote") {
    assert.equal(isManagedRemoteUrl(data.cover, config), true);
    assert.equal(isManagedRemoteUrl(data.referenceImage, config), true);
    assert.deepEqual(Object.keys(data).sort(), [
      "cover", "description", "imageN", "imageSize", "inputSchema", "key", "kind",
      "metadata", "preprocessSteps", "promptTemplate", "referenceImage", "title",
    ].sort());
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

test("dry-run reports duplicate cover and reference image bytes", async () => {
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

test("uploads one asset and writes a clean STYLE_REF JSON", async () => {
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
    const finalFile = path.join(value.output, "high-gloss-chrome-rendering.json");
    const finalData = JSON.parse(await readFile(finalFile, "utf8"));
    assert.equal(finalData.cover, finalData.referenceImage);
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
    await writeFile(
      path.join(duplicateDir, "style-template.json"),
      `${JSON.stringify(templateData(), null, 2)}\n`,
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
