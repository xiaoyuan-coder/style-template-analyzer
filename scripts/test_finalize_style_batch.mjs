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
    referenceType: "paired-images",
    referenceStructure: "paired-images",
    supportedModes: ["whole_image", "subject_only"],
    contentScope: "adaptive",
    contentStrategy: "primary_subject_reconstruction",
    modeInstructions: {
      whole_image: "保留整张输入画布的全部内容、文字、UI、布局与空间关系，并统一应用模板风格。",
      subject_only: "只提取并风格化主要主体，移除原背景和其他非主体内容，使用均匀纯白背景。",
    },
    referenceAssets: { source: "./same.png", style: "./same.png" },
    testAssets: { input: "./test.png", output: "./test.png" },
    testNotes: ["本地测试记录"],
    reviewNotes: ["待复核"],
    styleInstruction: "内容权限：当前输入图是主体、物件、场景、文字、视角和构图的唯一来源，保持本次模式范围内的身份、数量、姿态、轮廓、遮挡和空间关系。成像媒介：把全部可见区域完整重建为高反射抛光铬材质，让反射参与体积塑造。形体与细节：保留输入结构，以圆润连续曲面概括细小表面纹理。线条与边缘：外轮廓清晰，内部结构由反射边界和高光转折界定。笔触与纹理：表面光滑，无纸纹、颗粒和手绘笔触。色彩组织：中性银灰占主导，输入环境色只作为受控反射色带出现。明暗与空间：宽阔高光、深色反射带和柔和接触阴影建立体积，保持输入视角和布局。覆盖要求：主体、背景、文字、界面、边缘和角落统一重建，不保留原始哑光表面或未处理照片区域。去摄影化：全部可见区域以目标媒介重新构成，原照片像素、摄影皮肤、真实毛发、镜头景深、原始镜头光照和照片噪声必须完全消失。",
    contentExclusion: "参考内容禁迁移清单：具体气球、人物、道具、场景、服饰、姿势、文字、品牌、边框和装饰。以上内容不得影响裁切或构图，不要新增输入图不存在的物件或可读文字。",
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
