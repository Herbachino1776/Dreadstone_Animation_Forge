import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import zlib from "node:zlib";

import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";


function requireCondition(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}


async function loadGlb(filepath) {
  globalThis.self = globalThis;
  if (typeof globalThis.createImageBitmap !== "function") {
    globalThis.createImageBitmap = async () => ({
      width: 1,
      height: 1,
      close() {},
    });
  }
  const bytes = fs.readFileSync(filepath);
  const buffer = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  );
  const resourcePath =
    pathToFileURL(path.dirname(path.resolve(filepath))).href + "/";
  const loader = new GLTFLoader();
  return await new Promise((resolve, reject) => {
    loader.parse(buffer, resourcePath, resolve, reject);
  });
}


function allObjectsByName(scene) {
  const result = new Map();
  scene.traverse((object) => {
    if (object.name) {
      result.set(object.name, object);
    }
  });
  return result;
}


function setMorph(object, targetName, value) {
  requireCondition(
    object.morphTargetDictionary &&
      Object.hasOwn(object.morphTargetDictionary, targetName),
    `${object.name} has no Three.js morph target ${targetName}.`,
  );
  object.morphTargetInfluences[
    object.morphTargetDictionary[targetName]
  ] = value;
}


function manifestNodeNames(value) {
  if (Array.isArray(value)) {
    return value.flatMap(manifestNodeNames);
  }
  if (value && typeof value === "object") {
    return Object.values(value).flatMap(manifestNodeNames);
  }
  return typeof value === "string" && value ? [value] : [];
}


function parseGlb(filepath) {
  const bytes = fs.readFileSync(filepath);
  requireCondition(
    bytes.readUInt32LE(0) === 0x46546c67 &&
      bytes.readUInt32LE(4) === 2,
    "Runtime fixture is not a glTF 2.0 GLB.",
  );
  let offset = 12;
  let json = null;
  let binary = null;
  while (offset + 8 <= bytes.length) {
    const length = bytes.readUInt32LE(offset);
    const type = bytes.readUInt32LE(offset + 4);
    offset += 8;
    const chunk = bytes.subarray(offset, offset + length);
    offset += length;
    if (type === 0x4e4f534a) {
      json = JSON.parse(
        chunk.toString("utf8").replace(/[\u0000 \t\r\n]+$/u, ""),
      );
    } else if (type === 0x004e4942) {
      binary = chunk;
    }
  }
  requireCondition(json && binary, "GLB has no JSON or binary chunk.");
  return { json, binary };
}


function paethPredictor(left, above, upperLeft) {
  const prediction = left + above - upperLeft;
  const leftDistance = Math.abs(prediction - left);
  const aboveDistance = Math.abs(prediction - above);
  const cornerDistance = Math.abs(prediction - upperLeft);
  if (leftDistance <= aboveDistance && leftDistance <= cornerDistance) {
    return left;
  }
  return aboveDistance <= cornerDistance ? above : upperLeft;
}


function inspectRgbaPng(bytes) {
  requireCondition(
    bytes.subarray(0, 8).equals(
      Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    ),
    "Embedded stain image is not a PNG.",
  );
  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlace = 0;
  const compressed = [];
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString("ascii", offset + 4, offset + 8);
    const data = bytes.subarray(offset + 8, offset + 8 + length);
    offset += 12 + length;
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === "IDAT") {
      compressed.push(data);
    } else if (type === "IEND") {
      break;
    }
  }
  requireCondition(
    width > 0 &&
      height > 0 &&
      bitDepth === 8 &&
      colorType === 6 &&
      interlace === 0 &&
      compressed.length > 0,
    "Embedded stain PNG is not non-interlaced 8-bit RGBA.",
  );
  const filtered = zlib.inflateSync(Buffer.concat(compressed));
  const bytesPerPixel = 4;
  const stride = width * bytesPerPixel;
  requireCondition(
    filtered.length === (stride + 1) * height,
    "Embedded stain PNG scanline length is invalid.",
  );
  const pixels = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y += 1) {
    const filter = filtered[y * (stride + 1)];
    const sourceOffset = y * (stride + 1) + 1;
    const targetOffset = y * stride;
    for (let x = 0; x < stride; x += 1) {
      const raw = filtered[sourceOffset + x];
      const left =
        x >= bytesPerPixel
          ? pixels[targetOffset + x - bytesPerPixel]
          : 0;
      const above = y > 0 ? pixels[targetOffset + x - stride] : 0;
      const upperLeft =
        y > 0 && x >= bytesPerPixel
          ? pixels[targetOffset + x - stride - bytesPerPixel]
          : 0;
      let reconstructed;
      if (filter === 0) {
        reconstructed = raw;
      } else if (filter === 1) {
        reconstructed = raw + left;
      } else if (filter === 2) {
        reconstructed = raw + above;
      } else if (filter === 3) {
        reconstructed = raw + Math.floor((left + above) / 2);
      } else if (filter === 4) {
        reconstructed = raw + paethPredictor(left, above, upperLeft);
      } else {
        throw new Error(`Unsupported PNG filter ${filter}.`);
      }
      pixels[targetOffset + x] = reconstructed & 0xff;
    }
  }
  let visiblePixels = 0;
  let transparentPixels = 0;
  let featheredPixels = 0;
  for (let index = 3; index < pixels.length; index += 4) {
    const alpha = pixels[index];
    visiblePixels += alpha > 0 ? 1 : 0;
    transparentPixels += alpha === 0 ? 1 : 0;
    featheredPixels += alpha > 0 && alpha < 255 ? 1 : 0;
  }
  requireCondition(
    visiblePixels > 0 &&
      transparentPixels > 0 &&
      featheredPixels > 0,
    "Embedded stain PNG lacks required mask data: " +
      JSON.stringify({
        width,
        height,
        visiblePixels,
        transparentPixels,
        featheredPixels,
      }),
  );
  return {
    width,
    height,
    visiblePixels,
    transparentPixels,
    featheredPixels,
  };
}


async function main() {
  const [glbPath, manifestPath] = process.argv.slice(2);
  requireCondition(
    glbPath && manifestPath,
    "Usage: node surface_stain_three_runtime.mjs <asset.glb> <manifest.json>",
  );
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const glb = parseGlb(glbPath);
  const loaded = await loadGlb(glbPath);
  const objects = allObjectsByName(loaded.scene);
  const deformations = manifest.deformations;
  const bindings = deformations.surfaceStainMeshes;
  requireCondition(bindings.length > 0, "Manifest has no surface-stain meshes.");
  const textureInspection = {};
  const vertexColorInspection = {};

  for (const binding of bindings) {
    const object = objects.get(binding.nodeName);
    requireCondition(object, `GLTFLoader missed stain node ${binding.nodeName}.`);
    requireCondition(
      object.material,
      `${binding.nodeName} has no Three.js material.`,
    );
    const materials = Array.isArray(object.material)
      ? object.material
      : [object.material];
    const colorAttribute = object.geometry?.getAttribute("color");
    const usesVertexColor =
      binding.portableRepresentation === "VERTEX_COLOR_RGBA" ||
      binding.attributeSemantic === "COLOR_0";
    requireCondition(
      materials.every(
        (material) =>
          material.transparent &&
          (usesVertexColor ? material.vertexColors : material.map),
      ),
      `${binding.nodeName} did not load as a portable transparent glTF material.`,
    );
    requireCondition(
      object.userData.dsb_generated_role === "surface_stain_export",
      `${binding.nodeName} lost its glTF extras.`,
    );
    if (usesVertexColor) {
      requireCondition(
        binding.attributeSemantic === "COLOR_0" &&
          colorAttribute &&
          colorAttribute.itemSize === 4,
        `${binding.nodeName} has no RGBA COLOR_0 attribute.`,
      );
      const alphas = [];
      for (let index = 0; index < colorAttribute.count; index += 1) {
        alphas.push(colorAttribute.getW(index));
      }
      const minimumAlpha = Math.min(...alphas);
      const maximumAlpha = Math.max(...alphas);
      requireCondition(
        maximumAlpha > 0 && maximumAlpha - minimumAlpha > 1e-5,
        `${binding.nodeName} COLOR_0 does not contain a visible feathered mask.`,
      );
      vertexColorInspection[binding.nodeName] = {
        vertexCount: colorAttribute.count,
        minimumAlpha,
        maximumAlpha,
      };
    } else {
      const imageIndex = glb.json.images.findIndex(
        (image) => image.name === binding.textureName,
      );
      requireCondition(
        imageIndex >= 0,
        `${binding.nodeName} references no embedded GLB image.`,
      );
      const image = glb.json.images[imageIndex];
      const view = glb.json.bufferViews[image.bufferView];
      requireCondition(
        image.mimeType === "image/png" && view,
        `${binding.nodeName} does not use an embedded PNG buffer view.`,
      );
      const imageStart = view.byteOffset || 0;
      const imageBytes = glb.binary.subarray(
        imageStart,
        imageStart + view.byteLength,
      );
      textureInspection[binding.textureName] = inspectRgbaPng(
        imageBytes,
      );
    }
    object.visible = false;
  }
  for (const gore of deformations.generatedGoreMeshes) {
    const object = objects.get(gore.nodeName);
    requireCondition(object, `GLTFLoader missed gore node ${gore.nodeName}.`);
    object.visible = false;
  }
  requireCondition(
    bindings.every((binding) => !objects.get(binding.nodeName).visible),
    "Basis/rest shows a surface stain.",
  );

  const activation = {};
  for (const site of deformations.progressiveDamageSites) {
    for (const stage of site.stages) {
      for (const binding of bindings) {
        const object = objects.get(binding.nodeName);
        object.visible = false;
        setMorph(object, binding.morphTarget, 0);
      }
      for (const gore of deformations.generatedGoreMeshes) {
        objects.get(gore.nodeName).visible = false;
      }

      const expectedStains = new Set(
        stage.surfaceStainBindings.map((binding) => binding.nodeName),
      );
      for (const binding of stage.surfaceStainBindings) {
        const object = objects.get(binding.nodeName);
        requireCondition(
          object,
          `${stage.stage} references missing stain ${binding.nodeName}.`,
        );
        object.visible = true;
        setMorph(object, stage.deformationKeyName, 1);
      }
      const expectedGore = new Set(
        manifestNodeNames(stage.generatedNodeNames),
      );
      for (const nodeName of expectedGore) {
        const object = objects.get(nodeName);
        requireCondition(
          object,
          `${stage.stage} references missing gore node ${nodeName}.`,
        );
        object.visible = true;
      }

      const visibleStains = new Set(
        bindings
          .filter((binding) => objects.get(binding.nodeName).visible)
          .map((binding) => binding.nodeName),
      );
      requireCondition(
        visibleStains.size === expectedStains.size &&
          [...expectedStains].every((name) => visibleStains.has(name)),
        `${stage.stage} activated the wrong surface-stain assembly.`,
      );
      activation[stage.stage] = {
        stainNodes: [...visibleStains].sort(),
        goreNodes: [...expectedGore].sort(),
      };
    }
  }

  console.log(
    "THREE_SURFACE_STAIN_RUNTIME=" +
      JSON.stringify({
        status: "PASS",
        loader: "Three.js GLTFLoader",
        stainNodeCount: bindings.length,
        decodedTextureCount: Object.keys(textureInspection).length,
        vertexColorNodeCount: Object.keys(vertexColorInspection).length,
        basisHidden: true,
        activation,
      }),
  );
}


await main();
