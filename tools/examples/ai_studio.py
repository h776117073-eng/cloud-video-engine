import math
import os

import bpy
from mathutils import Vector

SCENE = bpy.context.scene
OUTPUT = os.environ.get("BLENDER_OUTPUT", "//ai_studio.mp4")

# Clean scene.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.curves, bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
    pass

# Render settings.
SCENE.render.engine = "BLENDER_EEVEE"
SCENE.render.resolution_x = 1920
SCENE.render.resolution_y = 1080
SCENE.render.resolution_percentage = 100
SCENE.render.fps = 30
SCENE.frame_start = 1
SCENE.frame_end = 150
SCENE.render.image_settings.media_type = "VIDEO"
SCENE.render.ffmpeg.format = "MPEG4"
SCENE.render.ffmpeg.codec = "H264"
SCENE.render.ffmpeg.audio_codec = "AAC"
SCENE.render.ffmpeg.constant_rate_factor = "MEDIUM"
SCENE.render.film_transparent = False
SCENE.render.filepath = OUTPUT

# World/background.
SCENE.world.color = (0.005, 0.008, 0.02)

# Helper for materials.
def make_material(name, base, metallic=0.0, roughness=0.4, emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*base, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat

gold = make_material(
    "Gold",
    (0.38, 0.16, 0.025),
    metallic=0.92,
    roughness=0.17,
    emission=(1.0, 0.20, 0.015),
    emission_strength=0.35,
)

dark = make_material("Dark Ground", (0.008, 0.012, 0.025), metallic=0.2, roughness=0.3)

# Main 3D text.
bpy.ops.object.text_add(location=(0, 0, 0.35), rotation=(math.radians(90), 0, 0))
text_obj = bpy.context.object
text_obj.name = "AI_STUDIO"
text_obj.data.body = "AI STUDIO"
text_obj.data.align_x = "CENTER"
text_obj.data.align_y = "CENTER"
text_obj.data.size = 2.35
text_obj.data.extrude = 0.12
text_obj.data.bevel_depth = 0.045
text_obj.data.bevel_resolution = 6
text_obj.data.space_character = 1.0
text_obj.data.materials.append(gold)

# Slight text animation.
text_obj.scale = (0.82, 0.82, 0.82)
text_obj.keyframe_insert(data_path="scale", frame=1)
text_obj.scale = (1.0, 1.0, 1.0)
text_obj.keyframe_insert(data_path="scale", frame=35)

# Circular platform.
bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=5.8, depth=0.3, location=(0, 0, -0.3))
platform = bpy.context.object
platform.data.materials.append(dark)
bevel = platform.modifiers.new("Soft bevel", "BEVEL")
bevel.width = 0.18
bevel.segments = 5

# Accent ring.
bpy.ops.mesh.primitive_torus_add(
    major_radius=4.7,
    minor_radius=0.035,
    major_segments=128,
    minor_segments=16,
    location=(0, 0, -0.1),
)
ring = bpy.context.object
ring.data.materials.append(gold)

# Camera.
bpy.ops.object.camera_add(location=(7.8, -7.8, 4.8))
camera = bpy.context.object
SCENE.camera = camera
camera.data.lens = 52

def look_at(obj, target=(0.0, 0.0, 0.65)):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

look_at(camera)
camera.location = (8.5, -8.5, 4.8)
camera.keyframe_insert(data_path="location", frame=1)
camera.keyframe_insert(data_path="rotation_euler", frame=1)

# One and a half cinematic orbits.
for frame, angle in ((75, math.radians(180)), (150, math.radians(360))):
    radius = 12.0
    camera.location = (
        radius * math.cos(angle),
        radius * math.sin(angle),
        4.8 + 0.8 * math.sin(angle * 0.5),
    )
    look_at(camera)
    camera.keyframe_insert(data_path="location", frame=frame)
    camera.keyframe_insert(data_path="rotation_euler", frame=frame)

# Key lights.
def add_area(name, location, energy, size, color):
    bpy.ops.object.light_add(type="AREA", location=location)
    lamp = bpy.context.object
    lamp.name = name
    lamp.data.energy = energy
    lamp.data.shape = "DISK"
    lamp.data.size = size
    lamp.data.color = color
    look_at(lamp, (0, 0, 0.5))
    return lamp

add_area("Key", (4, -4, 7), 1200, 5.0, (1.0, 0.62, 0.28))
add_area("Fill", (-4, -1, 4), 700, 4.0, (0.25, 0.45, 1.0))
add_area("Rim", (0, 5, 6), 1000, 3.0, (1.0, 0.25, 0.05))

# Color management.
if hasattr(SCENE.view_settings, "look"):
    try:
        SCENE.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

SCENE.frame_set(1)
