"use client";

import { ArtifactImage } from "./artifact-image";

/**
 * Thin wrapper kept for backward compat with existing callers. Delegates to
 * the unified ArtifactImage so the rotate/regenerate controls are available
 * everywhere the artifact is rendered.
 */
export function CampaignArtifactPreview({
  missionId,
  prompt,
}: {
  missionId: string;
  prompt: string;
}) {
  return (
    <ArtifactImage
      localMissionId={missionId}
      prompt={prompt}
      alt={`Mission ${missionId} artifact`}
      heightClass="h-[280px]"
    />
  );
}
