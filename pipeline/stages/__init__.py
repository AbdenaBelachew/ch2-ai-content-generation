"""Pipeline execution stages."""

from pipeline.stages.assembly import AssemblyStage
from pipeline.stages.keyframes import KeyframesStage
from pipeline.stages.music import MusicStage
from pipeline.stages.narration import NarrationStage
from pipeline.stages.script import ScriptStage
from pipeline.stages.shots import ShotsStage

__all__ = [
    "AssemblyStage",
    "KeyframesStage",
    "MusicStage",
    "NarrationStage",
    "ScriptStage",
    "ShotsStage",
]

