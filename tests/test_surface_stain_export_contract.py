import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "dreadstone_animation_forge"
    / "deformation"
    / "gltf_validation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "surface_stain_gltf_validation",
    MODULE_PATH,
)
GLTF_VALIDATION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GLTF_VALIDATION)


def fixture():
    stages = (
        ("LIGHT", "ScratchAlpha"),
        ("MEDIUM", "BrokenCrescent"),
        ("HEAVY", "CraterOmega"),
    )
    nodes = [
        {"name": "ATTACHED_HOST", "mesh": 0},
        {"name": "DETACHED_HOST", "mesh": 1},
    ]
    materials = [
        {
            "name": "BASE_MATERIAL",
            "pbrMetallicRoughness": {},
        }
    ]
    images = []
    textures = []
    meshes = [
        {"primitives": [{"material": 0}]},
        {"primitives": [{"material": 0}]},
    ]
    keys = []
    stage_records = []
    generated = []
    for stage_index, (stage_name, key_name) in enumerate(stages):
        bindings = []
        for role, source in (
            ("ATTACHED", "ATTACHED_HOST"),
            ("DETACHED", "DETACHED_HOST"),
        ):
            suffix = f"{stage_name}_{role}"
            node_name = "DSB_STAIN_" + suffix
            material_name = "DSB_STAIN_MAT_" + suffix
            image_name = "DSB_STAIN_RGBA_" + suffix
            material_index = len(materials)
            image_index = len(images)
            texture_index = len(textures)
            mesh_index = len(meshes)
            materials.append({
                "name": material_name,
                "alphaMode": "BLEND",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": texture_index},
                },
            })
            images.append({"name": image_name, "mimeType": "image/png"})
            textures.append({"source": image_index})
            meshes.append({
                "primitives": [
                    {
                        "material": material_index,
                        "targets": [{"POSITION": 0}],
                    }
                ],
                "extras": {"targetNames": [key_name]},
            })
            nodes.append({
                "name": node_name,
                "mesh": mesh_index,
                "extras": {
                    "dsb_generated_role": "surface_stain_export",
                    "dsb_stain_default_visible": False,
                    "dsb_preview_only": False,
                },
            })
            bindings.append({
                "schema": (
                    GLTF_VALIDATION.SURFACE_STAIN_BINDING_SCHEMA
                ),
                "nodeName": node_name,
                "materialName": material_name,
                "textureName": image_name,
                "deformationKey": key_name,
                "ownershipRole": role,
                "sourceObject": source,
                "morphTarget": key_name,
                "defaultVisible": False,
                "activationWeight": 0.01,
                "portableArtifactIncluded": True,
                "runtimeImplementationIncluded": False,
            })
        keys.append({
            "name": key_name,
            "regionId": "head",
            "regionMode": "PAIRED_SEGMENT",
            "goreOverlayEnabled": True,
            "goreOverlayMode": "STAIN_AND_RAISED",
            "surfaceStainBindings": copy.deepcopy(bindings),
        })
        stage_records.append({
            "stage": stage_name,
            "regionId": "head",
            "deformationKeyName": key_name,
            "surfaceStainBindings": copy.deepcopy(bindings),
        })
        raised_name = f"DSB_GORE_{stage_name}"
        raised_mesh_index = len(meshes)
        meshes.append({"primitives": [{"material": 0}]})
        nodes.append({"name": raised_name, "mesh": raised_mesh_index})
        generated.append({"nodeName": raised_name})
    gltf = {
        "asset": {"version": "2.0"},
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "images": images,
        "textures": textures,
    }
    manifest = {
        "deformations": {
            "keys": keys,
            "generatedGoreMeshes": generated,
            "progressiveDamageSites": [
                {
                    "runtimeImplementationIncluded": False,
                    "stages": stage_records,
                }
            ],
        }
    }
    return gltf, manifest


def convert_fixture_to_vertex_colors(gltf, manifest):
    gltf["accessors"] = []
    bindings = manifest["deformations"]["keys"]
    for key in bindings:
        for binding in key["surfaceStainBindings"]:
            binding.update({
                "textureName": "",
                "attributeName": "DSB_Surface_Stain_RGBA",
                "attributeSemantic": "COLOR_0",
                "maskEncoding": "COLOR_0_RGBA_ALPHA",
                "portableRepresentation": "VERTEX_COLOR_RGBA",
            })
            node = next(
                value
                for value in gltf["nodes"]
                if value.get("name") == binding["nodeName"]
            )
            mesh = gltf["meshes"][node["mesh"]]
            material = gltf["materials"][
                mesh["primitives"][0]["material"]
            ]
            material["pbrMetallicRoughness"].pop(
                "baseColorTexture",
                None,
            )
            accessor_index = len(gltf["accessors"])
            gltf["accessors"].append({"type": "VEC4"})
            mesh["primitives"][0].setdefault("attributes", {})[
                "COLOR_0"
            ] = accessor_index
            mesh["weights"] = [0.0]
    for site in manifest["deformations"]["progressiveDamageSites"]:
        by_key = {
            key["name"]: copy.deepcopy(key["surfaceStainBindings"])
            for key in bindings
        }
        for stage in site["stages"]:
            stage["surfaceStainBindings"] = by_key[
                stage["deformationKeyName"]
            ]
    return gltf, manifest


class SurfaceStainExportContractTests(unittest.TestCase):
    def test_complete_portable_stain_contract_passes(self):
        gltf, manifest = fixture()
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["surfaceStains"]["bindingCount"], 6)
        self.assertEqual(result["surfaceStains"]["progressiveStageCount"], 3)
        self.assertEqual(result["raisedGoreGeometry"]["status"], "PASS")

    def test_missing_stain_node_fails_distinct_surface_validation(self):
        gltf, manifest = fixture()
        gltf["nodes"] = [
            node
            for node in gltf["nodes"]
            if node.get("name") != "DSB_STAIN_LIGHT_ATTACHED"
        ]
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["surfaceStains"]["status"], "FAIL")
        self.assertEqual(result["raisedGoreGeometry"]["status"], "PASS")

    def test_missing_raised_node_fails_distinct_geometry_validation(self):
        gltf, manifest = fixture()
        gltf["nodes"] = [
            node
            for node in gltf["nodes"]
            if node.get("name") != "DSB_GORE_MEDIUM"
        ]
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["surfaceStains"]["status"], "PASS")
        self.assertEqual(result["raisedGoreGeometry"]["status"], "FAIL")

    def test_base_material_is_required(self):
        gltf, manifest = fixture()
        gltf["meshes"][0]["primitives"][0].pop("material")
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["baseMaterials"]["status"], "FAIL")

    def test_explicit_stage_mapping_cannot_be_swapped(self):
        gltf, manifest = fixture()
        stages = manifest["deformations"]["progressiveDamageSites"][0]["stages"]
        stages[0]["surfaceStainBindings"] = copy.deepcopy(
            stages[1]["surfaceStainBindings"]
        )
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(
            "explicitly assigned deformation key",
            " ".join(result["surfaceStains"]["errors"]),
        )

    def test_rgba_color_zero_representation_passes_without_texture(self):
        gltf, manifest = convert_fixture_to_vertex_colors(*fixture())
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["surfaceStains"]["bindingCount"], 6)

    def test_vertex_color_binding_requires_rgba_accessor(self):
        gltf, manifest = convert_fixture_to_vertex_colors(*fixture())
        gltf["accessors"][0]["type"] = "VEC3"
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(
            "no alpha channel",
            " ".join(result["surfaceStains"]["errors"]),
        )

    def test_nonzero_stain_morph_at_basis_fails(self):
        gltf, manifest = convert_fixture_to_vertex_colors(*fixture())
        first_binding = manifest["deformations"]["keys"][0][
            "surfaceStainBindings"
        ][0]
        node = next(
            value
            for value in gltf["nodes"]
            if value.get("name") == first_binding["nodeName"]
        )
        gltf["meshes"][node["mesh"]]["weights"] = [1.0]
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(
            "nonzero Basis/rest morph weight",
            " ".join(result["surfaceStains"]["errors"]),
        )


if __name__ == "__main__":
    unittest.main()
