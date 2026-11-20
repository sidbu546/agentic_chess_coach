import { ActionIcon, Alert, Badge, Box, Button, Group, Loader, ScrollArea, Stack, Switch, Text, Textarea, Tooltip } from "@mantine/core";
import {
  IconCircleCheck,
  IconCircleX,
  IconEye,
  IconEyeOff,
  IconHelpCircle,
  IconPlayerPlayFilled,
  IconSend,
  IconTrash,
  IconUser,
} from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { positionKey } from "@/api/chessApi";
import { askCoach, CoachApiError, COACH_API_URL } from "@/coach/coachApi";
import { playerId, sessionId, useCoach, type ChatMessage } from "@/coach/coachStore";
import { usePlayer } from "@/coach/playerStore";
import type { CheckedClaim, CoachLine } from "@/coach/types";
import { moveNumber, ROOT_ID, useCurrentNode, useGameTree } from "@/state/gameTree";
import { lineText, useLinePlayer } from "@/state/linePlayer";
import { useSettings } from "@/state/settings";
import { PlayerModal } from "./PlayerModal";

const SUGGESTIONS = [
  "What's the best move here, and why?",
  "What was wrong with the last move?",
  "What is my opponent threatening?",
  "What mistakes did I make this game?",
];

let msgCounter = 0;
const newMsgId = () => `msg${++msgCounter}`;

export function CoachPanel() {
  const node = useCurrentNode();
  const nodes = useGameTree((s) => s.nodes);
  const rootFen = nodes[ROOT_ID].fen;
  const { messages, shownId, add, update, show, clear } = useCoach();
  const [draft, setDraft] = useState("");
  const [thinkHarder, setThinkHarder] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const profile = usePlayer((s) => s.profile);
  const loadProfile = usePlayer((s) => s.load);
  const viewport = useRef<HTMLDivElement>(null);
  const busy = messages.some((m) => m.status === "pending");

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, messages.at(-1)?.status]);

  const where = (nodeId: string) => {
    const n = nodes[nodeId];
    if (!n?.move) return "start position";
    const mn = moveNumber(rootFen, n.ply);
    return `after ${mn.number}${mn.white ? "." : "..."} ${n.move.san}`;
  };

  const send = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setDraft("");
    const key = positionKey(node.position);
    const history = messages
      .filter((m) => m.status === "ok")
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.text, fen: m.fen }));
    add({ id: newMsgId(), role: "user", text: q, positionKey: key, nodeId: node.id, fen: node.fen, status: "ok" });
    const id = newMsgId();
    add({ id, role: "coach", text: "", positionKey: key, nodeId: node.id, fen: node.fen, status: "pending" });
    try {
      const res = await askCoach({
        question: q,
        position: node.position,
        last_move: node.move,
        player_id: playerId(),
        history,
        depth: thinkHarder ? "deep" : "auto",
        session_id: sessionId(),
        // The side at the bottom of the board is the player's side.
        player_color: useSettings.getState().orientation,
      });
      update(id, {
        status: "ok",
        text: res.answer,
        annotations: res.annotations,
        claims: res.claims,
        lines: res.lines ?? [],
        toolsUsed: res.tools_used,
        model: res.model,
        tier: res.tier,
        usage: res.usage,
      });
      if (res.annotations.arrows.length || res.annotations.highlights.length) show(id);
      loadProfile(); // the answer may have added a mistake or a session
    } catch (err) {
      const offline = err instanceof CoachApiError && err.offline;
      update(id, {
        status: "error",
        text: offline
          ? `The coach service isn't running at ${COACH_API_URL}. Start services/coach, then ask again.`
          : (err as Error).message,
      });
    }
  };

  return (
    <Box className="coach-panel">
      <ScrollArea className="chat-scroll" viewportRef={viewport} type="auto" offsetScrollbars>
        <Stack gap="sm" p="xs">
          {messages.length === 0 && (
            <Stack gap="xs" mt="md">
              <Text fw={600}>Ask your coach about this position</Text>
              <Text size="sm" c="dimmed">
                Answers are grounded in the chess service, and every chess claim is checked by <code>/v1/verify</code> before you see
                it.
              </Text>
              <Group gap={6} mt={4}>
                {SUGGESTIONS.map((s) => (
                  <Button key={s} size="compact-sm" variant="light" radius="xl" onClick={() => send(s)}>
                    {s}
                  </Button>
                ))}
              </Group>
            </Stack>
          )}
          {messages.map((m) => (
            <Message
              key={m.id}
              m={m}
              where={where(m.nodeId)}
              here={m.positionKey === positionKey(node.position)}
              shown={shownId === m.id}
              onToggleShow={() => show(shownId === m.id ? null : m.id)}
              onJump={() => {
                if (nodes[m.nodeId]) useGameTree.getState().goTo(m.nodeId);
                if (m.annotations) show(m.id);
              }}
              onPlay={(line) => {
                if (!nodes[m.nodeId]) return;
                useGameTree.getState().goTo(m.nodeId);
                show(null);
                useLinePlayer.getState().open(line, m.nodeId);
              }}
            />
          ))}
        </Stack>
      </ScrollArea>

      <Box className="chat-input">
        <Group justify="space-between" mb={6}>
          <Tooltip label="Use the stronger reasoning tier for this question (slower, costs more)" multiline maw={260}>
            <Switch
              size="xs"
              label="Think harder"
              checked={thinkHarder}
              onChange={(e) => setThinkHarder(e.currentTarget.checked)}
            />
          </Tooltip>
          <Group gap={6}>
            {draft.length > 3500 && (
              <Text size="xs" c={draft.length >= 4000 ? "red" : "dimmed"}>
                {draft.length}/4000
              </Text>
            )}
            <Tooltip label="Your level and how much detail the coach gives. Click to change.">
              <Button
                size="compact-xs"
                variant="light"
                color="gray"
                leftSection={<IconUser size={12} />}
                onClick={() => setProfileOpen(true)}
              >
                {profile ? `${cap(profile.level)} · ${profile.explanation_depth}` : "Profile"}
              </Button>
            </Tooltip>
          </Group>
        </Group>
        <Textarea
          placeholder="Ask about the position… (Enter to send, Shift+Enter for a new line)"
          autosize
          minRows={1}
          maxRows={5}
          maxLength={4000}
          value={draft}
          onChange={(e) => setDraft(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
          rightSectionWidth={70}
          rightSection={
            <Group gap={2} wrap="nowrap">
              {messages.length > 0 && (
                <Tooltip label="Clear conversation">
                  <ActionIcon variant="subtle" color="gray" onClick={clear} aria-label="Clear conversation">
                    <IconTrash size={16} />
                  </ActionIcon>
                </Tooltip>
              )}
              <ActionIcon variant="filled" onClick={() => send(draft)} disabled={!draft.trim() || busy} aria-label="Send">
                <IconSend size={16} />
              </ActionIcon>
            </Group>
          }
        />
      </Box>
      <PlayerModal opened={profileOpen} onClose={() => setProfileOpen(false)} />
    </Box>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function Message({
  m,
  where,
  here,
  shown,
  onToggleShow,
  onJump,
  onPlay,
}: {
  m: ChatMessage;
  where: string;
  here: boolean;
  shown: boolean;
  onToggleShow: () => void;
  onJump: () => void;
  onPlay: (line: CoachLine) => void;
}) {
  if (m.role === "user") {
    return (
      <Box className="msg msg-user">
        <Text size="sm">{m.text}</Text>
        <Text size="xs" c="dimmed" mt={2} className="msg-where" onClick={onJump}>
          {where}
        </Text>
      </Box>
    );
  }
  if (m.status === "pending") {
    return (
      <Group className="msg msg-coach" gap="xs">
        <Loader size="xs" type="dots" />
        <Text size="sm" c="dimmed">
          Analysing and checking claims…
        </Text>
      </Group>
    );
  }
  if (m.status === "error") {
    return (
      <Alert color="red" variant="light" p="xs">
        <Text size="sm">{m.text}</Text>
      </Alert>
    );
  }
  const hasShapes = !!m.annotations && (m.annotations.arrows.length > 0 || m.annotations.highlights.length > 0);
  return (
    <Box className="msg msg-coach">
      <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
        {m.text}
      </Text>
      {m.lines && m.lines.length > 0 && <Lines lines={m.lines} onPlay={onPlay} />}
      {m.claims && m.claims.length > 0 && <Claims claims={m.claims} />}
      <Group gap={6} mt={6} justify="space-between">
        <Group gap={4}>
          {m.tier && (
            <Tooltip
              label={
                m.usage
                  ? `${m.usage.llm_calls} model call(s) · ${m.usage.input_tokens.toLocaleString()} in (${m.usage.cached_tokens.toLocaleString()} cached) · ${m.usage.output_tokens.toLocaleString()} out (${m.usage.reasoning_tokens.toLocaleString()} reasoning)`
                  : m.model
              }
            >
              <Badge size="xs" variant="light" color={m.tier === "deep" ? "violet" : m.tier === "fallback" ? "orange" : "blue"}>
                {m.tier} · {m.model}
                {m.usage && m.usage.cost_usd > 0 ? ` · $${m.usage.cost_usd.toFixed(4)}` : ""}
              </Badge>
            </Tooltip>
          )}
          {m.toolsUsed?.map((t) => (
            <Badge key={t} size="xs" variant="outline" color="gray">
              {t}
            </Badge>
          ))}
        </Group>
        {hasShapes && (
          <Tooltip label={here ? (shown ? "Hide arrows" : "Show arrows on board") : `Go to the position (${where})`}>
            <ActionIcon size="sm" variant={shown && here ? "light" : "subtle"} onClick={here ? onToggleShow : onJump} aria-label="Toggle arrows">
              {shown && here ? <IconEye size={14} /> : <IconEyeOff size={14} />}
            </ActionIcon>
          </Tooltip>
        )}
      </Group>
    </Box>
  );
}

function Lines({ lines, onPlay }: { lines: CoachLine[]; onPlay: (line: CoachLine) => void }) {
  const playing = useLinePlayer((s) => s.line);
  return (
    <Stack gap={4} mt={8}>
      {lines.map((line, i) => {
        const last = line.steps[line.steps.length - 1];
        return (
          <Group key={i} className="line-chip" gap={8} wrap="nowrap" justify="space-between">
            <Text size="xs" style={{ fontVariantNumeric: "tabular-nums" }} lineClamp={2}>
              {lineText(line)}
            </Text>
            <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
              {last.state === "checkmate" && (
                <Badge size="xs" color="red" variant="light">
                  mate
                </Badge>
              )}
              <Button
                size="compact-xs"
                variant={playing === line ? "filled" : "light"}
                leftSection={<IconPlayerPlayFilled size={11} />}
                onClick={() => onPlay(line)}
              >
                Play
              </Button>
            </Group>
          </Group>
        );
      })}
    </Stack>
  );
}

function Claims({ claims }: { claims: CheckedClaim[] }) {
  return (
    <Stack gap={2} mt={8} className="claims">
      {claims.map((c, i) => {
        const v = c.result.verdict;
        const Icon = v === "supported" ? IconCircleCheck : v === "refuted" ? IconCircleX : IconHelpCircle;
        const color = v === "supported" ? "teal" : v === "refuted" ? "red" : "gray";
        return (
          <Tooltip
            key={i}
            label={c.checked ? `Coach wrote: “${c.text}” · Verifier: ${c.result.reason}` : c.result.reason}
            multiline
            maw={340}
            openDelay={300}
          >
            <Group gap={6} wrap="nowrap" align="flex-start">
              <Icon size={14} color={`var(--mantine-color-${color}-5)`} style={{ flexShrink: 0, marginTop: 2 }} />
              {/* Show what was actually checked, so a tick never claims more than the verifier tested. */}
              <Text size="xs" c={v === "supported" ? undefined : "dimmed"} td={v === "refuted" ? "line-through" : undefined}>
                {c.checked || c.text}
              </Text>
            </Group>
          </Tooltip>
        );
      })}
    </Stack>
  );
}
