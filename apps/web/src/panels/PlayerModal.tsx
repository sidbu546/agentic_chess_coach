import { Alert, Badge, Button, Divider, Group, Modal, NumberInput, SegmentedControl, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { getSessions } from "@/coach/coachApi";
import { playerId } from "@/coach/coachStore";
import { usePlayer } from "@/coach/playerStore";
import type { ExplanationDepth, Level, SessionSummary } from "@/coach/types";

const LEVELS: { value: Level; label: string; hint: string }[] = [
  { value: "beginner", label: "Beginner", hint: "under ~1200" },
  { value: "intermediate", label: "Intermediate", hint: "~1200–1800" },
  { value: "advanced", label: "Advanced", hint: "1800+" },
];
const DEPTHS: { value: ExplanationDepth; label: string }[] = [
  { value: "short", label: "Short" },
  { value: "normal", label: "Normal" },
  { value: "detailed", label: "Detailed" },
];

const ago = (ts: number) => {
  const s = Date.now() / 1000 - ts;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString();
};

export function PlayerModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { profile, error, load, save, forget } = usePlayer();
  const [rating, setRating] = useState<number | string>("");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [confirmForget, setConfirmForget] = useState(false);

  useEffect(() => {
    if (!opened) return;
    setConfirmForget(false);
    load();
    getSessions(playerId()).then(setSessions, () => setSessions([]));
  }, [opened, load]);

  useEffect(() => setRating(profile?.rating ?? ""), [profile?.rating]);

  const saveRating = () => {
    const r = typeof rating === "number" ? rating : null;
    if (r === (profile?.rating ?? null)) return;
    save({ rating: r });
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Your coach profile" size="md">
      {error && (
        <Alert color="red" variant="light" mb="sm" p="xs">
          <Text size="sm">{error}</Text>
        </Alert>
      )}
      {profile && (
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            The coach uses this to pitch its explanations. It is stored by the coach service for this browser only.
          </Text>

          <Stack gap={6}>
            <Group justify="space-between">
              <Text size="sm" fw={600}>
                Level
              </Text>
              <Text size="xs" c="dimmed">
                {profile.level_source === "chosen" ? "chosen by you" : profile.level_source === "rating" ? "from your rating" : "default"}
              </Text>
            </Group>
            <SegmentedControl
              fullWidth
              value={profile.level}
              onChange={(v) => save({ level: v as Level })}
              data={LEVELS.map((l) => ({ value: l.value, label: l.label }))}
            />
            <Text size="xs" c="dimmed">
              {LEVELS.find((l) => l.value === profile.level)?.hint}
              {profile.level_source === "chosen" && profile.rating != null && (
                <>
                  {" · "}
                  <Text span size="xs" c="blue" style={{ cursor: "pointer" }} onClick={() => save({ level: null })}>
                    use my rating instead
                  </Text>
                </>
              )}
            </Text>
          </Stack>

          <NumberInput
            label="Rating (optional)"
            description="Sets your level automatically unless you pick one above"
            placeholder="e.g. 1100"
            min={100}
            max={3500}
            allowDecimal={false}
            value={rating}
            onChange={setRating}
            onBlur={saveRating}
            onKeyDown={(e) => e.key === "Enter" && saveRating()}
          />

          <Stack gap={6}>
            <Text size="sm" fw={600}>
              Explanations
            </Text>
            <SegmentedControl
              fullWidth
              value={profile.explanation_depth}
              onChange={(v) => save({ explanation_depth: v as ExplanationDepth })}
              data={DEPTHS}
            />
          </Stack>

          <Divider />

          <Stack gap={6}>
            <Text size="sm" fw={600}>
              Mistakes the coach has noticed
            </Text>
            {profile.recurring_mistakes.length === 0 ? (
              <Text size="xs" c="dimmed">
                None yet. Ask "What was wrong with my last move?" after a move and the coach will keep track of patterns.
              </Text>
            ) : (
              profile.recurring_mistakes.map((m) => (
                <Group key={m.theme} gap="xs" wrap="nowrap" align="flex-start">
                  <Badge size="sm" variant="light" color={m.count >= 2 ? "orange" : "gray"} style={{ flexShrink: 0 }}>
                    ×{m.count}
                  </Badge>
                  <Stack gap={0}>
                    <Text size="sm">{m.label}</Text>
                    <Text size="xs" c="dimmed">
                      Last: {m.last_example.detail} ({ago(m.last_seen)})
                    </Text>
                  </Stack>
                </Group>
              ))
            )}
          </Stack>

          <Stack gap={6}>
            <Text size="sm" fw={600}>
              Past sessions
            </Text>
            {sessions.length === 0 ? (
              <Text size="xs" c="dimmed">
                No questions yet.
              </Text>
            ) : (
              sessions.slice(0, 5).map((s) => (
                <Stack key={s.session_id} gap={0}>
                  <Text size="xs" fw={500}>
                    {ago(s.ended)} · {s.questions} question{s.questions === 1 ? "" : "s"}
                  </Text>
                  <Text size="xs" c="dimmed" lineClamp={2}>
                    {s.topics.join(" · ")}
                  </Text>
                </Stack>
              ))
            )}
          </Stack>

          <Divider />

          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              {profile.stats.questions} question{profile.stats.questions === 1 ? "" : "s"} in {profile.stats.sessions} session
              {profile.stats.sessions === 1 ? "" : "s"}
            </Text>
            {confirmForget ? (
              <Group gap="xs">
                <Button size="compact-xs" variant="subtle" color="gray" onClick={() => setConfirmForget(false)}>
                  Cancel
                </Button>
                <Button
                  size="compact-xs"
                  color="red"
                  onClick={async () => {
                    await forget();
                    setSessions([]);
                    setConfirmForget(false);
                  }}
                >
                  Delete everything
                </Button>
              </Group>
            ) : (
              <Button size="compact-xs" variant="subtle" color="red" onClick={() => setConfirmForget(true)}>
                Forget me
              </Button>
            )}
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
