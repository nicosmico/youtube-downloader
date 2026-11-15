"""Routes of the presets: `/api/presets` CRUD."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from app.errors import ApiError
from app.jobs.options import AudioFormatName, Mode, QualityName, check_options
from app.presets.repository import PresetNameTaken, PresetRepository

MAX_NAME = 40


class CreatePreset(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    mode: Mode
    quality: QualityName | None = None
    audio_format: AudioFormatName | None = Field(default=None, alias="audioFormat")


class UpdatePreset(BaseModel):
    """Every field optional. Sending any of mode/quality/audioFormat replaces the whole options
    group (what is left out becomes empty), so a switch of mode never keeps a stale field."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    mode: Mode | None = None
    quality: QualityName | None = None
    audio_format: AudioFormatName | None = Field(default=None, alias="audioFormat")


def _clean_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise ApiError(422, "invalid_name", "Escribe un nombre para el preset.")
    if len(name) > MAX_NAME:
        raise ApiError(
            422, "invalid_name", f"El nombre del preset admite hasta {MAX_NAME} caracteres."
        )
    return name


def _name_taken(name: str) -> ApiError:
    return ApiError(409, "preset_name_taken", f"Ya existe un preset llamado «{name}».")


def _not_found() -> ApiError:
    return ApiError(404, "preset_not_found", "No se encontró el preset.")


def build_presets_router(*, repo: PresetRepository) -> APIRouter:
    router = APIRouter(prefix="/api/presets")

    @router.get("")
    def list_presets() -> list[dict[str, Any]]:
        return [p.to_dict() for p in repo.list_presets()]

    @router.post("", status_code=201)
    def create_preset(body: CreatePreset) -> dict[str, Any]:
        name = _clean_name(body.name)
        check_options(body.mode, body.quality, body.audio_format)
        try:
            preset = repo.create(
                name=name, mode=body.mode, quality=body.quality, audio_format=body.audio_format
            )
        except PresetNameTaken:
            raise _name_taken(name) from None
        return preset.to_dict()

    @router.patch("/{preset_id}")
    def update_preset(preset_id: str, body: UpdatePreset) -> dict[str, Any]:
        current = repo.get(preset_id)
        if current is None:
            raise _not_found()
        sent = body.model_fields_set
        if "name" in sent and body.name is None:
            raise ApiError(422, "invalid_name", "Escribe un nombre para el preset.")
        name = _clean_name(body.name) if body.name is not None else current.name
        mode, quality, audio_format = current.mode, current.quality, current.audio_format
        if sent & {"mode", "quality", "audio_format"}:
            mode = body.mode or current.mode
            quality, audio_format = body.quality, body.audio_format
            check_options(mode, quality, audio_format)  # type: ignore[arg-type]
        try:
            updated = repo.update(
                preset_id, name=name, mode=mode, quality=quality, audio_format=audio_format
            )
        except PresetNameTaken:
            raise _name_taken(name) from None
        if updated is None:  # deleted between the read and the write
            raise _not_found()
        return updated.to_dict()

    @router.delete("/{preset_id}", status_code=204)
    def delete_preset(preset_id: str) -> Response:
        if not repo.delete(preset_id):
            raise _not_found()
        return Response(status_code=204)

    return router
