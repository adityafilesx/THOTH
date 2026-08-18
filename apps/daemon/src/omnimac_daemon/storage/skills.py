"""Skill store over the `skills` table. Lists installed SkillDefinitions and
toggles their enabled flag. No seed data — an empty store is the honest state
until the skill engine ships."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from omnimac_daemon.schemas import SkillDefinition
from omnimac_daemon.storage.models import SkillRow


class SkillStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_skills(self) -> list[SkillDefinition]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(SkillRow))).scalars().all()
            return [SkillDefinition.model_validate(r.definition_json) for r in rows]

    async def add_skill(self, skill: SkillDefinition) -> SkillDefinition:
        async with self._session_factory() as session:
            session.add(
                SkillRow(
                    id=skill.id,
                    name=skill.name,
                    definition_json=skill.model_dump(mode="json"),
                    enabled=skill.enabled,
                )
            )
            await session.commit()
            return skill

    async def get_skill(self, skill_id: str) -> SkillDefinition | None:
        async with self._session_factory() as session:
            row = await session.get(SkillRow, skill_id)
            return SkillDefinition.model_validate(row.definition_json) if row else None

    async def set_enabled(self, skill_id: str, enabled: bool) -> SkillDefinition | None:
        async with self._session_factory() as session:
            row = await session.get(SkillRow, skill_id)
            if row is None:
                return None
            row.enabled = enabled
            data = dict(row.definition_json)
            data["enabled"] = enabled
            row.definition_json = data
            await session.commit()
            return SkillDefinition.model_validate(data)
