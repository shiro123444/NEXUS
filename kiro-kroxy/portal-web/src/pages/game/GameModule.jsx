import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  Gamepad2,
  Trophy,
  History as HistoryIcon,
  RefreshCw,
  ArrowLeft,
  ArrowRight,
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  SkipForward,
  BookOpen,
  X as CloseIcon,
  FastForward,
  Play,
  Pause,
  LogOut as ExitIcon,
  Image as ImageIcon,
  Medal,
  Users as UsersIcon,
  Store,
  Search,
  Gift,
  Tag,
  ShoppingBag,
  Clock3,
  UserRound,
  CheckCircle2,
  XCircle,
  Eye,
  Send,
  Layers3,
} from "lucide-react";
import { SoulLantern, SoulLanternLoader } from "../../components/SoulLantern";

/**
 * GameModule — entry point for the AI adventure module.
 *
 * From M4b on we ship 6 genres (xianxia / campus / isekai / detective /
 * wasteland / ghost_tale) — the backend rolls one at random per run unless
 * the client passes a slug. The header says "世界"; the per-run genre
 * shows up in the top bar inside the adventure view.
 */
const GENRE_LABELS = {
  xianxia:    { name: "修仙",       tagline: "入定一刻，世界自开" },
  campus:     { name: "校园谜踪",   tagline: "夕阳教室与未寄出的告白" },
  isekai:     { name: "异界纪年",   tagline: "System 在你眼前展开" },
  detective:  { name: "沪上谜案",   tagline: "雨夜霓虹下，证人不止一个" },
  wasteland:  { name: "末日纪元",   tagline: "燃料与水，是新的银两" },
  ghost_tale: { name: "异闻录",     tagline: "供奉未足，归途无门" },
  neo_future: { name: "都市余震",   tagline: "信号之外，还有一个你" },
  deep_sea:   { name: "海底城邦",   tagline: "潮汐带走证词，灯塔留在海下" },
  memory_court: { name: "记忆法庭", tagline: "证词可以剪辑，罪名不能撤回" },
  time_train: { name: "逆时列车",   tagline: "下一站是昨天，车票只剪一次" },
};

/**
 * Per-genre state dashboard configuration. Each entry maps a state key
 * (that the LLM populates via prompts.state_extras) to a display label and
 * a tone hint — the HeroCard renders them in this order, falling back to
 * location/mood when a genre has no custom keys.
 *
 * Keys here must match exactly what prompts.py asks the LLM to set. If you
 * change one side, change the other — otherwise the chip never fires.
 */
const GENRE_STATE_CONFIG = {
  xianxia: [
    { key: "realm",     label: "境界", tone: "indigo" },
    { key: "qi",        label: "灵力", tone: "emerald" },
    { key: "dao_heart", label: "道心", tone: "rose" },
    { key: "sect",      label: "宗门", tone: "slate" },
  ],
  campus: [
    { key: "club",          label: "社团", tone: "indigo" },
    { key: "rep",           label: "风评", tone: "emerald" },
    { key: "crush",         label: "倾心", tone: "rose" },
    { key: "secret_known",  label: "秘闻", tone: "violet" },
  ],
  isekai: [
    { key: "class", label: "职业", tone: "indigo" },
    { key: "level", label: "等级", tone: "amber" },
    { key: "gold",  label: "金币", tone: "amber" },
    { key: "party", label: "同伴", tone: "emerald" },
  ],
  detective: [
    { key: "clues",      label: "线索", tone: "amber" },
    { key: "suspicion",  label: "疑犯", tone: "rose" },
    { key: "alibi",      label: "证词", tone: "slate" },
  ],
  wasteland: [
    { key: "rad",         label: "辐射", tone: "rose" },
    { key: "fuel",        label: "燃料", tone: "amber" },
    { key: "faction_rep", label: "派系", tone: "slate" },
  ],
  ghost_tale: [
    { key: "karma",         label: "业",   tone: "violet" },
    { key: "offerings",     label: "供奉", tone: "amber" },
    { key: "taboo_broken",  label: "破忌", tone: "rose" },
  ],
  neo_future: [
    { key: "phone_battery", label: "电量", tone: "emerald" },
    { key: "trust_score",   label: "信任", tone: "indigo" },
    { key: "lead",          label: "线索", tone: "amber" },
  ],
  deep_sea: [
    { key: "oxygen", label: "氧气", tone: "emerald" },
    { key: "depth",  label: "深度", tone: "indigo" },
    { key: "debt",   label: "债务", tone: "rose" },
    { key: "sonar",  label: "声呐", tone: "amber" },
  ],
  memory_court: [
    { key: "evidence",         label: "证据", tone: "amber" },
    { key: "credibility",      label: "可信", tone: "indigo" },
    { key: "objection",        label: "异议", tone: "rose" },
    { key: "protected_memory", label: "封存", tone: "slate" },
  ],
  time_train: [
    { key: "carriage",    label: "车厢", tone: "indigo" },
    { key: "ticket",      label: "车票", tone: "amber" },
    { key: "lost_future", label: "失去", tone: "rose" },
    { key: "next_station", label: "下站", tone: "emerald" },
  ],
};

const COMMON_STATE_FALLBACK = [
  { key: "location", label: "此刻", tone: "indigo" },
  { key: "mood",     label: "心境", tone: "rose" },
];

function genreOf(run) {
  const slug = (run?.genre || run?.world_bible?.genre || "xianxia").toLowerCase();
  return GENRE_LABELS[slug] || GENRE_LABELS.xianxia;
}
export default function GameModule({ user, api }) {
  const [view, setView] = useState("home");
  const [active, setActive] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [startElapsed, setStartElapsed] = useState(0);
  const [toast, setToast] = useState(null);
  const startControllerRef = useRef(null);

  // Debug hook for reviewing the SoulLantern loader without burning token
  // on a real world-gen. Visiting ?preview=lantern parks the overlay on
  // screen and fast-forwards elapsed time so we can eyeball both the
  //世界 and 封面 phases. Remove the query string to exit.
  const previewLantern =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("preview") === "lantern";

  async function refreshActive() {
    try {
      const { data } = await api.gameActiveRun();
      setActive(data.run || null);
      return data.run || null;
    } catch (err) {
      setActive(null);
      return null;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshActive();
  }, []);

  // Tick a seconds counter while the world generation is in flight — lets
  // the overlay show elapsed time instead of a silent 30-60s wait.
  useEffect(() => {
    if (previewLantern) return; // preview effect drives the counter instead
    if (!starting) {
      setStartElapsed(0);
      return;
    }
    const t0 = Date.now();
    const id = setInterval(() => {
      setStartElapsed(Math.floor((Date.now() - t0) / 1000));
    }, 500);
    return () => clearInterval(id);
  }, [starting, previewLantern]);

  // Preview mode: when ?preview=lantern is set, drive the overlay through
  // a scripted elapsed cycle (0 → 90s, loop). No API calls, no token burn.
  useEffect(() => {
    if (!previewLantern) return;
    setStarting(true);
    const t0 = Date.now();
    const id = setInterval(() => {
      const e = Math.floor((Date.now() - t0) / 1000) % 90;
      setStartElapsed(e);
    }, 500);
    return () => clearInterval(id);
  }, [previewLantern]);

  function flashToast(message, tone = "info") {
    setToast({ message, tone });
    setTimeout(() => setToast(null), 2600);
  }

  async function handleStart(genreSlug) {
    if (starting) return;
    setStarting(true);
    let succeeded = false;
    const controller = new AbortController();
    startControllerRef.current = controller;
    const body = genreSlug ? { genre: genreSlug } : {};
    try {
      await api.gameStartRun(body, { signal: controller.signal });
      await refreshActive();
      succeeded = true;
      flashToast("世界已生成", "success");
    } catch (err) {
      // Aborted by user via cancel button — best-effort cleanup via
      // refreshActive (the server may have persisted an `abandoned` run
      // already if generate_world failed mid-flight).
      if (err?.name === "CanceledError" || err?.code === "ERR_CANCELED") {
        await refreshActive();
        flashToast("已取消生成", "info");
        startControllerRef.current = null;
        setStarting(false);
        return;
      }
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 409) {
        flashToast("你已经有一个进行中的冒险", "warn");
        await refreshActive();
        succeeded = true;
      } else if (status === 502) {
        flashToast(
          typeof detail === "string" ? detail : "世界生成失败，稍后再试",
          "error"
        );
      } else {
        flashToast(typeof detail === "string" ? detail : "启动失败", "error");
      }
    } finally {
      startControllerRef.current = null;
      if (succeeded) {
        // Let the genre-reveal card sit on its "settled" frame for a beat
        // before we clear starting and switch into the adventure view —
        // otherwise the揭晓 flashes by too fast to read.
        setTimeout(() => {
          setStarting(false);
          setView("adventure");
        }, 1200);
      } else {
        setStarting(false);
      }
    }
  }

  function handleCancelStart() {
    if (startControllerRef.current) {
      startControllerRef.current.abort();
    }
  }

  function handleEnter() {
    if (active) setView("adventure");
  }

  async function handleAbandon() {
    if (!active) return;
    if (!window.confirm("确定放弃当前冒险？状态将被标记为 abandoned。")) return;
    try {
      await api.gameAbandon(active.id);
      await refreshActive();
      setView("home");
      flashToast("已放弃当前冒险", "info");
    } catch (err) {
      flashToast("放弃失败", "error");
    }
  }

  return (
    <motion.div
      key="game-root"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="space-y-6"
    >
      <Header view={view} onView={setView} hasActive={!!active} />

      <AnimatePresence>
        {starting && (
          <GenreRevealOverlay
            key="reveal"
            settled={active ? genreOf(active).name : null}
            elapsed={startElapsed}
            onCancel={handleCancelStart}
          />
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {view === "home" && (
          <HomeView
            key="home"
            active={active}
            loading={loading}
            starting={starting}
            onStart={handleStart}
            onAbandon={handleAbandon}
            onEnter={handleEnter}
          />
        )}
        {view === "adventure" && (
          <AdventureGalgame
            key="adventure"
            api={api}
            active={active}
            onBack={() => setView("home")}
            onAbandon={handleAbandon}
            onRefresh={refreshActive}
          />
        )}
        {view === "leaderboard" && <LeaderboardView key="leaderboard" api={api} />}
        {view === "history" && <HistoryView key="history" api={api} />}
        {view === "gallery" && <GalleryView key="gallery" api={api} />}
        {view === "achievements" && <AchievementsView key="achievements" api={api} />}
        {view === "market" && <MarketView key="market" api={api} />}
        {view === "trades" && <TradesView key="trades" api={api} />}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -20, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: -20, x: "-50%" }}
            className={`fixed top-6 left-1/2 z-[100] px-4 py-3 rounded-2xl text-sm font-semibold shadow-xl backdrop-blur ${
              toast.tone === "success"
                ? "bg-emerald-500/90 text-white"
                : toast.tone === "error"
                ? "bg-red-500/90 text-white"
                : toast.tone === "warn"
                ? "bg-amber-500/90 text-white"
                : "bg-slate-800/90 text-white"
            }`}
          >
            {toast.message}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function Header({ view, onView, hasActive }) {
  const items = [
    { id: "home", label: "冒险", icon: Gamepad2 },
    { id: "gallery", label: "画廊", icon: ImageIcon },
    { id: "achievements", label: "成就", icon: Medal },
    { id: "market", label: "市场", icon: Store },
    { id: "trades", label: "交易", icon: ArrowLeftRight },
    { id: "leaderboard", label: "榜单", icon: Trophy },
    { id: "history", label: "历程", icon: HistoryIcon },
  ];
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-800 dark:text-white flex items-center gap-3">
          世界
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          短篇分幕冒险。每局都有目标、伏笔、转折和结局。
        </p>
      </div>
      <div className="flex items-center gap-1 p-1 rounded-2xl bg-white/60 dark:bg-slate-900/60 backdrop-blur border border-slate-200 dark:border-slate-800">
        {items.map((it) => {
          const isActive = view === it.id || (it.id === "home" && view === "adventure");
          return (
            <button
              key={it.id}
              onClick={() => onView(it.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition ${
                isActive
                  ? "bg-slate-800 text-white shadow"
                  : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/50"
              }`}
            >
              <it.icon size={16} />
              {it.label}
              {it.id === "home" && hasActive && view !== "adventure" ? (
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function HomeView({ active, loading, starting, onStart, onAbandon, onEnter }) {
  // Genre picker: "" means blind-box (server rolls weighted random).
  const [pickedGenre, setPickedGenre] = useState("");
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="space-y-6"
    >
      <div className="relative overflow-hidden rounded-3xl border border-slate-200 dark:border-slate-800 bg-gradient-to-br from-indigo-500/10 via-purple-500/10 to-pink-500/10 p-8">
        <div className="absolute inset-0 pixel-scanlines opacity-40" />
        <div className="relative flex flex-col md:flex-row md:items-end gap-6">
          <div className="flex-1">
            <div className="inline-flex px-3 py-1 rounded-full bg-white/70 dark:bg-slate-900/70 text-xs font-semibold text-indigo-600 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-500/30">
              自由 · 探索 · 相遇
            </div>
            <h2 className="mt-4 text-2xl md:text-3xl font-extrabold tracking-tight text-slate-800 dark:text-white">
              你好，这里是「世界」。
            </h2>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 max-w-xl">
              一款由 NEXUS 实时驱动的文字冒险游戏。每次开局都会生成新的时代、人物和暗线；
              你做出的选择会被记住，也会在之后回到你面前。
            </p>

            {!active && (
              <GenrePicker picked={pickedGenre} onPick={setPickedGenre} disabled={starting} />
            )}

            <div className="mt-6 flex flex-wrap items-center gap-3">
              {active ? (
                <>
                  <button
                    onClick={onEnter}
                    className="px-5 py-3 rounded-2xl bg-indigo-600 text-white font-bold shadow hover:bg-indigo-500 transition flex items-center gap-2"
                  >
                    <Gamepad2 size={16} /> 进入冒险
                  </button>
                  <button
                    onClick={onAbandon}
                    className="px-5 py-3 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-bold hover:bg-slate-50 dark:hover:bg-slate-800 transition"
                  >
                    放弃当前
                  </button>
                </>
              ) : (
                <button
                  onClick={() => onStart(pickedGenre || null)}
                  disabled={starting}
                  className="px-5 py-3 rounded-2xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-bold shadow hover:shadow-lg transition disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {starting ? (
                    <>
                      <motion.span animate={{ rotate: 360 }} transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }} className="inline-block">
                        <RefreshCw size={16} />
                      </motion.span>
                      造物中（约 40-60 秒）…
                    </>
                  ) : (
                    <>
                      {pickedGenre ? `开启【${GENRE_LABELS[pickedGenre]?.name || pickedGenre}】` : "开启新的冒险"}
                    </>
                  )}
                </button>
              )}
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {active
                  ? "公测期完全免费，每人同时仅限 1 个进行中的冒险。"
                  : pickedGenre
                  ? "已指定题材 · 也可重新选择『盲抽』。"
                  : "不指定题材即盲抽；系统会尽量避开你最近玩过的题材。"}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {[
          {
            title: "世界圣经",
            desc: "它不是说明书，而是故事的底牌。开局只放下欲望、关系和几条可能的路。",
          },
          {
            title: "分幕推进",
            desc: "不是每回合都逼你三选一。多数时候，世界会先回应你刚做过的事。",
          },
          {
            title: "伏笔回收",
            desc: "旧线索会回来，人物也会变化。故事会走向终局，不会无止境原地打转。",
          },
        ].map((item, idx) => (
          <div
            key={item.title}
            className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-900/60 backdrop-blur p-5"
          >
            <div className="flex items-baseline gap-2">
              <span className="text-[11px] font-black tracking-widest text-indigo-500 dark:text-indigo-300">
                {String(idx + 1).padStart(2, "0")}
              </span>
              <div className="text-sm font-extrabold tracking-wide text-slate-800 dark:text-slate-100">
                {item.title}
              </div>
            </div>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {item.desc}
            </p>
          </div>
        ))}
      </div>

      {loading ? null : active ? (
        <ActiveRunCard run={active} />
      ) : null}
    </motion.div>
  );
}

function GenrePicker({ picked, onPick, disabled }) {
  const slugs = Object.keys(GENRE_LABELS);
  const pickedLabel = picked ? GENRE_LABELS[picked]?.name || picked : "盲抽（推荐）";
  const pickedTag = picked
    ? GENRE_LABELS[picked]?.tagline
    : "从题材池里抽一个，并尽量避开最近重复出现的类型。";
  return (
    <div className="mt-5">
      <div className="pixel-font text-[10px] tracking-[0.3em] uppercase text-slate-500 dark:text-slate-400 mb-2">
        题材 · {pickedLabel}
      </div>
      <div className="flex flex-wrap gap-1.5">
        <GenreChip
          label="盲抽"
          active={!picked}
          disabled={disabled}
          onClick={() => onPick("")}
        />
        {slugs.map((slug) => (
          <GenreChip
            key={slug}
            label={GENRE_LABELS[slug]?.name || slug}
            active={picked === slug}
            disabled={disabled}
            onClick={() => onPick(slug)}
          />
        ))}
      </div>
      <div className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
        {pickedTag}
      </div>
    </div>
  );
}

function GenreChip({ label, icon, active, disabled, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition ${
        active
          ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900 border-slate-900 dark:border-white shadow"
          : "bg-white/70 dark:bg-slate-900/60 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-700 hover:bg-white dark:hover:bg-slate-800"
      } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
    >
      {icon ? <span className="mr-1">{icon}</span> : null}
      {label}
    </button>
  );
}

// Lantern caption pool — a handful of two-step phrases that rotate while
// the world + cover are generating. The boundary at ~25s / ~55s tracks the
// two backend phases (world-gen → cover-paint); within each phase we
// cycle flavor lines so the card doesn't feel static.
const LANTERN_LINES_WORLD = [
  "纸骨初成 · 描摹山河",
  "魂气将定 · 召唤众生",
  "因果初落 · 铺开命纸",
];
const LANTERN_LINES_COVER = [
  "灯芯点火 · 画师执笔",
  "像素落定 · 轮廓渐明",
  "最后一笔 · 即将成画",
];

function GenreRevealOverlay({ settled, elapsed = 0, onCancel }) {
  // While the backend is generating, cycle the title through the catalogue
  // every ~120ms — gives the "rolling slot machine" feel. When `settled`
  // shows up (the actual genre name picked by the server), pin to it.
  const slugs = useMemo(() => Object.keys(GENRE_LABELS), []);
  const [cycleIdx, setCycleIdx] = useState(0);

  useEffect(() => {
    if (settled) return;
    const id = setInterval(() => {
      setCycleIdx((i) => (i + 1) % slugs.length);
    }, 110);
    return () => clearInterval(id);
  }, [settled, slugs.length]);

  const display = settled
    ? { name: settled, tagline: Object.values(GENRE_LABELS).find((g) => g.name === settled)?.tagline || "" }
    : GENRE_LABELS[slugs[cycleIdx]];

  // Two-phase copy: elapsed <25s the world is being generated; beyond that
  // the cover image pipeline is usually the bottleneck. Each phase gets
  // its own flavor-rotation pool so the lantern doesn't feel muted.
  const inCoverPhase = elapsed >= 25;
  const phaseLabel = inCoverPhase ? "封面绘制中" : "世界生成中";
  const phaseLines = inCoverPhase ? LANTERN_LINES_COVER : LANTERN_LINES_WORLD;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/85 backdrop-blur-md px-6"
    >
      <motion.div
        initial={{ scale: 0.96 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="relative w-full max-w-md rounded-3xl border border-white/10 bg-gradient-to-br from-indigo-500/15 via-purple-500/10 to-pink-500/10 p-10 text-center overflow-hidden"
      >
        <div className="absolute inset-0 pixel-scanlines opacity-30 pointer-events-none" />
        <div className="pixel-font text-[11px] tracking-[0.4em] uppercase text-indigo-300 mb-4">
          {settled ? "天命已抽" : "执天命中…"}
        </div>
        <motion.div
          key={display.name}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: settled ? 0.6 : 0.18 }}
          className="text-4xl md:text-5xl font-extrabold text-white tracking-tight mb-3"
        >
          {display.name}
        </motion.div>
        <motion.div
          key={`${display.name}-line`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.85 }}
          transition={{ duration: settled ? 0.6 : 0.2, delay: settled ? 0.2 : 0 }}
          className="text-sm text-slate-300 max-w-xs mx-auto leading-relaxed"
        >
          {display.tagline}
        </motion.div>
        {!settled && (
          <div className="mt-8 flex flex-col items-center gap-3">
            <SoulLanternLoader
              size={84}
              lines={phaseLines}
              footnote={
                <>
                  {phaseLabel} · {elapsed > 0 ? `已耗时 ${elapsed}s` : "通常 45-80s"}
                </>
              }
            />
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="mt-1 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 text-[10px] text-slate-200 hover:bg-white/20 transition"
              >
                取消并返回
              </button>
            )}
          </div>
        )}
        {settled && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.4 }}
            className="mt-8 text-[11px] text-indigo-300 pixel-font tracking-widest"
          >
            进入剧场…
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  );
}

function ActiveRunCard({ run }) {
  const g = genreOf(run);
  return (
    <div className="rounded-3xl border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50/60 dark:bg-indigo-500/10 p-6">
      <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-300 font-bold">
        <Gamepad2 size={18} /> 进行中的冒险 · Run #{run.id}
        <span className="ml-2 px-2 py-0.5 rounded-full bg-white/70 dark:bg-slate-900/70 text-[11px] tracking-widest pixel-font text-indigo-500 dark:text-indigo-200 border border-indigo-200/60 dark:border-indigo-500/30">
          {g.name}
        </span>
      </div>
      <div className="mt-2 text-sm text-slate-600 dark:text-slate-300">
        第 {run.chapter_idx} 幕 · 第 {run.turn_idx} 回合 · 状态 {run.status}
      </div>
    </div>
  );
}

/* ── Galgame Adventure ───────────────────────────────────────────────────────
 * Fullscreen theater view: renders via React portal into document.body so it
 * escapes the parent admin/dashboard chrome. Narrative is split into sentences
 * and revealed one at a time; click / space / enter advances.
 */

function AdventureGalgame({ api, active, onBack, onAbandon, onRefresh }) {
  const [run, setRun] = useState(active);
  const [scenes, setScenes] = useState([]);
  const [sceneIdx, setSceneIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [acting, setActing] = useState(false);
  const [actError, setActError] = useState(null);
  const [drawer, setDrawer] = useState(false);
  const [awardToasts, setAwardToasts] = useState([]);
  const pollRef = useRef(null);
  const streamAbortRef = useRef(null);

  // Auto-dismiss achievement toasts — we keep at most MAX_TOAST_STACK on
  // screen and evict the oldest every 2.6s. Multiple awards landing together
  // no longer queue up behind each other.
  useEffect(() => {
    if (awardToasts.length === 0) return;
    const id = setTimeout(() => {
      setAwardToasts((prev) => prev.slice(1));
    }, 2600);
    return () => clearTimeout(id);
  }, [awardToasts]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
      if (streamAbortRef.current) {
        streamAbortRef.current.abort();
        streamAbortRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!active?.id) return;
    let alive = true;
    (async () => {
      try {
        const { data } = await api.gameRunDetail(active.id);
        if (!alive) return;
        setRun(data.run || null);
        const list = data.scenes || [];
        setScenes(list);
        // Resume at the latest turn — last scene in the chronological list.
        setSceneIdx(Math.max(0, list.length - 1));
      } catch (err) {
        if (alive) setError(err?.response?.data?.detail || "加载失败");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [active?.id, api]);

  useEffect(() => {
    if (!run || run.cover_url) return;
    pollRef.current = setInterval(async () => {
      try {
        const fresh = await onRefresh();
        if (fresh?.cover_url) {
          setRun((prev) => ({ ...(prev || {}), cover_url: fresh.cover_url }));
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* ignore */
      }
    }, 3500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [run, onRefresh]);

  // Per-turn CG poll: when the latest scene has no image_url yet, poll the
  // /scenes endpoint from that turn until the backend image pipeline fills
  // it in. Stops as soon as the newest persisted scene has an image or the
  // active run changes.
  useEffect(() => {
    if (!run?.id) return;
    const latest = scenes[scenes.length - 1];
    if (!latest || latest.live) return;
    if (latest.image_url) return;
    const fromTurn = Number(latest.turn_idx || 0);
    let alive = true;
    const id = setInterval(async () => {
      try {
        const { data } = await api.gameRunScenes(run.id, fromTurn);
        if (!alive) return;
        const fresh = (data.scenes || []).reduce((acc, s) => {
          acc[Number(s.turn_idx)] = s;
          return acc;
        }, {});
        setScenes((prev) => {
          let touched = false;
          const next = prev.map((s) => {
            if (s.live) return s;
            const f = fresh[Number(s.turn_idx)];
            if (f && f.image_url && !s.image_url) {
              touched = true;
              return { ...s, image_url: f.image_url };
            }
            return s;
          });
          return touched ? next : prev;
        });
      } catch {
        /* ignore transient errors */
      }
    }, 4500);
    return () => {
      alive = false;
      clearInterval(id);
    };
    // Depend on latest scene's id / image_url so poll restarts for each new turn.
  }, [run?.id, scenes.length, scenes[scenes.length - 1]?.id, scenes[scenes.length - 1]?.image_url, api]);

  const currentScene = scenes[sceneIdx] || null;
  const narrative = currentScene?.narrative || "";
  const isLive = !!currentScene?.live;
  // Always paginate — even during streaming. `splitSentences` is stable at
  // the prefix: as more text arrives, earlier pages don't change, only
  // later pages grow or get appended. The typewriter's `resetKey` uses
  // (turn_idx, idx), so within one page the cursor keeps advancing on each
  // delta; only when the player taps to next page does it reset.
  const sentences = useMemo(() => splitSentences(narrative), [narrative]);
  const choices = (currentScene?.choices || []).map((c) =>
    typeof c === "string" ? c : c.text || ""
  );
  const isEnded = (run?.status || "") === "ended";
  const isLatestScene = sceneIdx === scenes.length - 1;

  async function handleAct(choiceText, choiceIndex) {
    if (acting || !run?.id) return;
    setActing(true);
    setActError(null);

    // Optimistically append a live placeholder scene that the UI treats as
    // the active row. onDelta will mutate its `narrative`; onMeta will swap
    // it with the persisted scene from the server.
    const projectedTurn = (run?.turn_idx ?? 0) + 1;
    const placeholder = {
      id: `live-${Date.now()}`,
      turn_idx: projectedTurn,
      narrative: "",
      choices: [],
      player_action: choiceText,
      image_url: null,
      live: true,
    };
    setScenes((prev) => [...prev, placeholder]);
    setSceneIdx((prev) => prev + 1);

    const controller = api.gameActStream(run.id, choiceText, choiceIndex, {
      onStart: () => {
        // no-op — placeholder already rendered.
      },
      onDelta: ({ text }) => {
        if (!text) return;
        setScenes((prev) => {
          const next = prev.slice();
          const last = next[next.length - 1];
          if (!last?.live) return prev;
          next[next.length - 1] = { ...last, narrative: (last.narrative || "") + text };
          return next;
        });
      },
      onMeta: ({ run: nextRun, scene: nextScene, awards }) => {
        if (nextRun) setRun(nextRun);
        if (Array.isArray(awards) && awards.length > 0) {
          setAwardToasts((prev) => [...prev, ...awards]);
        }
        setScenes((prev) => {
          const next = prev.slice();
          const last = next[next.length - 1];
          if (last?.live && nextScene) {
            // Merge — keep the narrative the client accumulated so the
            // typewriter doesn't rewind, but pick up authoritative fields
            // (choices, image_url, turn_idx) from the server.
            next[next.length - 1] = {
              ...nextScene,
              narrative: last.narrative || nextScene.narrative || "",
              live: false,
              streamed: true,
            };
          } else if (nextScene) {
            next.push({ ...nextScene, streamed: true });
          } else if (last?.live) {
            next[next.length - 1] = { ...last, live: false, streamed: true };
          }
          return next;
        });
      },
      onError: ({ detail }) => {
        setActError(typeof detail === "string" ? detail : "回合推进失败，稍后再试");
        // Freeze the placeholder in place — narrative stays visible, no choices.
        setScenes((prev) => {
          const next = prev.slice();
          const last = next[next.length - 1];
          if (last?.live) next[next.length - 1] = { ...last, live: false };
          return next;
        });
        setActing(false);
        streamAbortRef.current = null;
      },
      onDone: () => {
        setActing(false);
        streamAbortRef.current = null;
      },
    });
    streamAbortRef.current = controller;
  }

  const content = (
    <div className="fixed inset-0 z-[200] bg-black text-white overflow-hidden select-none">
      <BackdropCover run={run} scene={currentScene} />
      {loading || !run ? (
        <LoadingOverlay error={error} onBack={onBack} />
      ) : (
        <GalgamePlayer
          run={run}
          scene={currentScene}
          sceneIdx={sceneIdx}
          sceneCount={scenes.length}
          sentences={sentences}
          choices={choices}
          acting={acting}
          actError={actError}
          isEnded={isEnded}
          isLatestScene={isLatestScene}
          isLive={isLive}
          onAct={handleAct}
          onOpenDrawer={() => setDrawer(true)}
          onBack={onBack}
          onAbandon={onAbandon}
          onDismissActError={() => setActError(null)}
          onSceneIdx={setSceneIdx}
        />
      )}
      <AnimatePresence>
        {isEnded && isLatestScene && (
          <EpilogueOverlay key="epilogue" run={run} onBack={onBack} />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {awardToasts.length > 0 && (
          <AwardStack key="award-stack" awards={awardToasts} />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {drawer && run && (
          <WorldDrawer
            key="drawer"
            run={run}
            onClose={() => setDrawer(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );

  return createPortal(content, document.body);
}

// Max characters we're willing to put on a single typewriter page before
// force-splitting. Chinese narrative @ 17-22 chars/sentence stays under 42,
// but the model occasionally emits a comma-joined clause chain that blows
// past that — paginating by 42 keeps the dialogue box from ballooning.
const MAX_PAGE_CHARS = 42;
const SOFT_BREAKS = /[，、；：—…]/;

function splitSentences(text) {
  if (!text) return [];
  const paragraphs = text
    .split(/\n\s*\n+/)
    .map((p) => p.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const sentenceRe = /[^。！？…]+[。！？…]+|[^。！？…]+$/g;
  const pages = [];
  for (const p of paragraphs) {
    const matches = p.match(sentenceRe) || [p];
    for (const raw of matches) {
      const piece = raw.trim();
      if (!piece) continue;
      if (piece.length <= MAX_PAGE_CHARS) {
        pages.push(piece);
        continue;
      }
      // Long sentence — try to break at soft punctuation first, then fall
      // back to a hard char-count split so we never publish a page wider
      // than the dialogue box can comfortably show.
      let remaining = piece;
      while (remaining.length > MAX_PAGE_CHARS) {
        const window = remaining.slice(0, MAX_PAGE_CHARS);
        let cut = -1;
        for (let i = window.length - 1; i > MAX_PAGE_CHARS * 0.5; i -= 1) {
          if (SOFT_BREAKS.test(window[i])) {
            cut = i + 1;
            break;
          }
        }
        if (cut < 0) cut = MAX_PAGE_CHARS;
        pages.push(remaining.slice(0, cut).trim());
        remaining = remaining.slice(cut).trim();
      }
      if (remaining) pages.push(remaining);
    }
  }
  return pages.length ? pages : [text];
}

function LoadingOverlay({ error, onBack }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-center px-6">
      {error ? (
        <>
          <div className="text-base text-red-300 font-semibold">{error}</div>
          <button
            onClick={onBack}
            className="mt-2 px-4 py-2 rounded-xl bg-white/10 border border-white/20 text-sm"
          >
            返回
          </button>
        </>
      ) : (
        <>
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
          >
            <RefreshCw className="text-indigo-300" size={22} />
          </motion.div>
          <div className="text-sm text-slate-300">拉取冒险中…</div>
        </>
      )}
    </div>
  );
}

function BackdropCover({ run, scene }) {
  const sceneImage = scene?.image_url || null;
  const desired = sceneImage || run?.cover_url || null;
  // Hold the last fully-loaded URL; only swap once the new URL has decoded.
  // Prevents the "blank canvas while text already visible" flash.
  const [ready, setReady] = useState(null);

  useEffect(() => {
    if (!desired) return;
    if (desired === ready) return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (!cancelled) setReady(desired);
    };
    img.onerror = () => {
      if (!cancelled) setReady(desired); // fall through to attempt render anyway
    };
    img.src = desired;
    return () => {
      cancelled = true;
    };
  }, [desired, ready]);

  const cover = ready;
  return (
    <div className="absolute inset-0 pixel-canvas">
      <AnimatePresence mode="wait">
        {cover ? (
          <motion.img
            key={cover}
            src={cover}
            alt="cover"
            initial={{ opacity: 0, scale: 1.04 }}
            animate={{ opacity: 1, scale: 1.02 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.6, ease: "easeOut" }}
            className="absolute inset-0 w-full h-full object-cover"
          />
        ) : (
          <motion.div
            key="ph"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-slate-900 via-black to-indigo-950 text-slate-500"
          >
            <SoulLanternLoader
              size={72}
              lines={["封面绘制中", "像素渐明", "灯芯未冷"]}
              footnote="稍等片刻"
            />
          </motion.div>
        )}
      </AnimatePresence>
      <div className="absolute inset-0 bg-gradient-to-b from-black/50 via-black/10 to-black/80 pointer-events-none" />
      <div className="absolute inset-0 pixel-scanlines opacity-40 pointer-events-none" />
    </div>
  );
}

function GalgamePlayer({
  run,
  scene,
  sceneIdx,
  sceneCount,
  sentences,
  choices,
  acting,
  actError,
  isEnded,
  isLatestScene,
  isLive,
  onAct,
  onOpenDrawer,
  onBack,
  onAbandon,
  onDismissActError,
  onSceneIdx,
}) {
  const reduced = useReducedMotion();
  const [idx, setIdx] = useState(0);
  const [lineDone, setLineDone] = useState(false);
  const [autoPlay, setAutoPlay] = useState(false);
  const [pickedIdx, setPickedIdx] = useState(null);
  // Require an extra advance tap after the final sentence before choices
  // pop up. Otherwise the overlay covers the last line before the player
  // has had time to read it.
  const [choicesArmed, setChoicesArmed] = useState(false);

  // Reset the typewriter cursor whenever the scene changes (new turn narrative).
  useEffect(() => {
    setIdx(0);
    setLineDone(false);
    setPickedIdx(null);
    setChoicesArmed(false);
  }, [sceneIdx]);

  const hasMore = idx < sentences.length - 1;
  const atEnd = idx >= sentences.length - 1 && lineDone;
  const currentLine = sentences[idx] || "";
  // Beat kind is derived from the scene payload: a scene beat has no choices,
  // a choice beat has >= 2 choices. Ending beats also have no choices but set
  // `isEnded`. History scenes (non-latest) just let the player scrub.
  const isChoiceBeat = choices.length > 0;
  const isSceneBeat = !isChoiceBeat && !isEnded && isLatestScene;
  const isHistory = !isLatestScene;
  // While streaming, hide the choices overlay — the scene has no choices yet,
  // and the typewriter is still chasing a growing buffer.
  const showChoices =
    !isLive &&
    atEnd &&
    choicesArmed &&
    isLatestScene &&
    !isEnded &&
    isChoiceBeat;
  const showEndingHint = !isLive && atEnd && isLatestScene && isEnded;
  const canContinueScene = !isLive && atEnd && isSceneBeat && !acting;
  const awaitingContinue = canContinueScene && !choicesArmed;
  // History mode: skip the typewriter entirely so回看 feels like flipping
  // pages of a finished book rather than replaying them.
  const historyForceDone = isHistory;

  // CTA label / state driven centrally so both the DialogueBox pill and the
  // keyboard handler agree on what "advance" means right now.
  let ctaLabel = null;
  let ctaTone = "idle"; // idle | primary | warn | muted
  if (isHistory) {
    ctaLabel = "回到最新 ▶";
    ctaTone = "muted";
  } else if (isLive) {
    ctaLabel = null;
  } else if (!lineDone) {
    ctaLabel = "跳过打字 ▶";
    ctaTone = "idle";
  } else if (hasMore) {
    ctaLabel = "继续 ▶";
    ctaTone = "idle";
  } else if (showEndingHint) {
    ctaLabel = "命途已定";
    ctaTone = "muted";
  } else if (showChoices) {
    ctaLabel = null; // choices own the screen
  } else if (isChoiceBeat && !choicesArmed) {
    ctaLabel = "展开选项 ▼";
    ctaTone = "primary";
  } else if (isSceneBeat) {
    ctaLabel = acting ? "推演中…" : "继续推进 ▶";
    ctaTone = acting ? "muted" : "primary";
  }

  function advance() {
    if (isHistory) {
      onSceneIdx && onSceneIdx(sceneCount - 1);
      return;
    }
    if (isLive) return;
    if (showChoices) return; // player must click a choice card
    if (!lineDone) {
      setLineDone(true);
      return;
    }
    if (hasMore) {
      setIdx((i) => i + 1);
      setLineDone(false);
      return;
    }
    // At the last sentence with line done — one more tap either arms the
    // choices overlay (choice beat) or auto-advances the scene (scene beat).
    if (!choicesArmed) {
      setChoicesArmed(true);
      if (isSceneBeat && !acting) {
        onAct("（继续）", -1);
      }
    }
  }

  function goPrev() {
    if (!onSceneIdx) return;
    if (sceneIdx > 0) onSceneIdx(sceneIdx - 1);
  }

  function goNext() {
    if (!onSceneIdx) return;
    if (sceneIdx < sceneCount - 1) onSceneIdx(sceneIdx + 1);
  }

  useEffect(() => {
    function onKey(e) {
      if (e.key === " " || e.key === "Enter" || e.key === "ArrowRight") {
        // ArrowRight in history means "next page"; space/enter mean advance.
        if (e.key === "ArrowRight" && isHistory && sceneIdx < sceneCount - 1) {
          e.preventDefault();
          goNext();
          return;
        }
        e.preventDefault();
        advance();
      } else if (e.key === "ArrowLeft") {
        if (sceneIdx > 0) {
          e.preventDefault();
          goPrev();
        }
      } else if (e.key === "Escape") {
        onBack();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // advance/onBack are recreated every render; that's fine — the effect
    // reattaches each time so the handler always closes over latest state.
  });

  useEffect(() => {
    if (isHistory) return;
    if (!autoPlay || !lineDone) return;
    const t = setTimeout(() => {
      if (hasMore) {
        setIdx((i) => i + 1);
        setLineDone(false);
      } else if (!choicesArmed) {
        setChoicesArmed(true);
        if (isSceneBeat && !acting) {
          onAct("（继续）", -1);
        }
      }
    }, 1400);
    return () => clearTimeout(t);
  }, [autoPlay, lineDone, hasMore, choicesArmed, isSceneBeat, acting, onAct, isHistory]);

  function skipAll() {
    setIdx(sentences.length - 1);
    setLineDone(true);
    if (isHistory) return;
    if (!choicesArmed) {
      setChoicesArmed(true);
      if (isSceneBeat && !acting) {
        onAct("（继续）", -1);
      }
    }
  }

  function handlePick(choiceText, choiceIndex) {
    if (acting) return;
    setPickedIdx(choiceIndex);
    onAct(choiceText, choiceIndex);
  }

  return (
    <>
      <TopBar
        run={run}
        autoPlay={autoPlay}
        onToggleAuto={() => setAutoPlay((v) => !v)}
        onSkip={skipAll}
        onOpenDrawer={onOpenDrawer}
        onExit={onBack}
        onAbandon={onAbandon}
      />

      {/* Full-screen advance layer. Disabled whenever a modal-like overlay
          owns the screen (choices) so clicking through to "advance" can't
          accidentally submit a turn. */}
      {!showChoices && (
        <button
          type="button"
          onClick={advance}
          aria-label={isHistory ? "回到最新" : "推进"}
          className="absolute inset-0 z-[210] cursor-pointer focus:outline-none"
        />
      )}

      <AnimatePresence>
        {showChoices && (
          <ChoicesOverlay
            key={`choices-${sceneIdx}`}
            choices={choices}
            acting={acting}
            pickedIdx={pickedIdx}
            onPick={handlePick}
          />
        )}
      </AnimatePresence>

      <DialogueBox
        line={currentLine}
        speed={reduced || historyForceDone ? 0 : 55}
        done={lineDone || historyForceDone}
        onDone={() => setLineDone(true)}
        idx={idx}
        total={sentences.length}
        hasMore={hasMore}
        showingChoices={showChoices}
        turnIdx={scene?.turn_idx ?? 0}
        endingHint={showEndingHint}
        live={isLive}
        awaitingChoicesArm={
          !isLive && atEnd && !choicesArmed && !isEnded && isChoiceBeat
        }
        awaitingContinue={awaitingContinue}
        isHistory={isHistory}
        sceneIdx={sceneIdx}
        sceneCount={sceneCount}
        ctaLabel={ctaLabel}
        ctaTone={ctaTone}
        onAdvance={advance}
        onPrev={goPrev}
        onNext={goNext}
        onReturnLatest={() => onSceneIdx && onSceneIdx(sceneCount - 1)}
        playerAction={scene?.player_action}
      />

      <AnimatePresence>
        {actError && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            onClick={onDismissActError}
            className="absolute bottom-44 left-1/2 -translate-x-1/2 z-[230] px-4 py-2 rounded-xl bg-red-500/90 text-white text-xs font-semibold shadow-xl cursor-pointer"
          >
            {actError}（点击关闭）
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function TopBar({ run, autoPlay, onToggleAuto, onSkip, onOpenDrawer, onExit, onAbandon }) {
  const g = genreOf(run);
  return (
    <div className="absolute top-0 left-0 right-0 z-[240] flex items-center justify-between gap-4 px-6 py-4 bg-gradient-to-b from-black/60 to-transparent">
      <div className="flex items-center gap-2 text-xs text-slate-200/80">
        <span className="pixel-font">{g.name}</span>
        <span className="opacity-50">·</span>
        <span className="opacity-80">
          Run #{run.id} · 第 {run.chapter_idx} 幕 · 第 {run.turn_idx} 回合
        </span>
      </div>
      <div className="flex items-center gap-2">
        <TopButton
          onClick={onToggleAuto}
          icon={autoPlay ? <Pause size={13} /> : <Play size={13} />}
          label={autoPlay ? "Auto" : "Auto"}
          active={autoPlay}
        />
        <TopButton onClick={onSkip} icon={<FastForward size={13} />} label="Skip" />
        <TopButton onClick={onOpenDrawer} icon={<BookOpen size={13} />} label="档案" />
        <TopButton
          onClick={onAbandon}
          icon={<CloseIcon size={13} />}
          label="放弃"
          danger
        />
        <TopButton onClick={onExit} icon={<ExitIcon size={13} />} label="退出" />
      </div>
    </div>
  );
}

function TopButton({ onClick, icon, label, active, danger }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick && onClick();
      }}
      className={`relative z-[241] inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-semibold backdrop-blur transition ${
        active
          ? "bg-indigo-500 text-white"
          : danger
          ? "bg-white/10 hover:bg-red-500/60 text-white border border-white/20"
          : "bg-white/10 hover:bg-white/20 text-white border border-white/20"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function DialogueBox({
  line,
  speed,
  done,
  onDone,
  idx,
  total,
  hasMore,
  showingChoices,
  turnIdx,
  endingHint,
  live,
  awaitingChoicesArm,
  awaitingContinue,
  isHistory,
  sceneIdx,
  sceneCount,
  ctaLabel,
  ctaTone,
  onAdvance,
  onPrev,
  onNext,
  onReturnLatest,
  playerAction,
}) {
  const canPrev = typeof onPrev === "function" && sceneIdx > 0;
  const canNext =
    typeof onNext === "function" && sceneIdx < (sceneCount || 0) - 1;
  const statusText = live
    ? "回合流式生成中…"
    : isHistory
    ? `回看 · 第 ${sceneIdx + 1} / ${sceneCount} 页`
    : done
    ? endingHint
      ? "命途已定"
      : awaitingChoicesArm
      ? "点击 / 空格 展开选项"
      : awaitingContinue
      ? "点击 / 空格 继续推进"
      : hasMore
      ? "点击 / 空格 继续"
      : "选择你的命途"
    : "打字中…";

  return (
    <div className="absolute left-0 right-0 bottom-0 z-[220] px-4 md:px-10 pb-6 md:pb-10 pointer-events-none">
      <motion.div
        key={`${turnIdx}-${idx}`}
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className={`mx-auto max-w-4xl rounded-3xl bg-black/70 backdrop-blur-md border px-6 md:px-8 py-5 md:py-6 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)] pointer-events-auto ${
          isHistory ? "border-amber-300/30" : "border-white/15"
        }`}
      >
        <div className="flex items-center justify-between mb-2 text-[10px] tracking-widest uppercase text-indigo-300/80 pixel-font">
          <span className={isHistory ? "text-amber-300/80" : undefined}>
            {isHistory ? "回看 · " : ""}
            {turnIdx === 0 ? "序章" : `第 ${turnIdx} 回`} ·{" "}
            {live
              ? "推演中"
              : `${String(idx + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}`}
          </span>
          {!showingChoices && (
            <span className="text-slate-400/70">{statusText}</span>
          )}
        </div>
        {live && playerAction && playerAction !== "（继续）" && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-3 text-[12px] text-indigo-200/80 italic border-l-2 border-indigo-400/60 pl-3"
          >
            你：{playerAction}
          </motion.div>
        )}
        <Typewriter
          text={line}
          speed={speed}
          forceDone={done}
          onDone={onDone}
          resetKey={`${turnIdx}-${idx}`}
          live={live}
          className="text-[17px] md:text-[19px] leading-loose text-slate-50 font-[450]"
        />
        <DialogueFooter
          canPrev={canPrev}
          canNext={canNext}
          isHistory={isHistory}
          ctaLabel={ctaLabel}
          ctaTone={ctaTone}
          onAdvance={onAdvance}
          onPrev={onPrev}
          onNext={onNext}
          onReturnLatest={onReturnLatest}
          sceneCount={sceneCount}
          sceneIdx={sceneIdx}
        />
      </motion.div>
    </div>
  );
}

function DialogueFooter({
  canPrev,
  canNext,
  isHistory,
  ctaLabel,
  ctaTone,
  onAdvance,
  onPrev,
  onNext,
  onReturnLatest,
  sceneCount,
  sceneIdx,
}) {
  // Nothing to render if we have no nav + no CTA (e.g. mid-stream).
  if (!ctaLabel && !canPrev && !canNext && !isHistory) return null;

  const stopProp = (fn) => (e) => {
    e.stopPropagation();
    fn && fn();
  };

  const ctaClass =
    ctaTone === "primary"
      ? "bg-indigo-500 hover:bg-indigo-400 text-white border-indigo-300/60"
      : ctaTone === "warn"
      ? "bg-amber-500/80 hover:bg-amber-400 text-white border-amber-300/60"
      : ctaTone === "muted"
      ? "bg-white/10 text-slate-300 border-white/10 cursor-default"
      : "bg-white/10 hover:bg-white/20 text-white border-white/20";

  return (
    <div className="mt-4 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <NavChip
          label="上一回"
          icon={<ChevronLeft size={13} />}
          onClick={stopProp(onPrev)}
          disabled={!canPrev}
        />
        <NavChip
          label="下一回"
          icon={<ChevronRight size={13} />}
          iconRight
          onClick={stopProp(onNext)}
          disabled={!canNext}
        />
        {isHistory && (
          <button
            type="button"
            onClick={stopProp(onReturnLatest)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-semibold bg-amber-500/15 border border-amber-400/40 text-amber-200 hover:bg-amber-500/25 transition"
          >
            <SkipForward size={13} /> 返回最新（{sceneCount}）
          </button>
        )}
      </div>
      {ctaLabel && (
        <button
          type="button"
          onClick={stopProp(onAdvance)}
          className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-[12px] font-bold border shadow-[0_6px_20px_-6px_rgba(0,0,0,0.5)] transition ${ctaClass}`}
          aria-label={ctaLabel}
        >
          {ctaLabel}
        </button>
      )}
    </div>
  );
}

function NavChip({ label, icon, iconRight, onClick, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-[11px] font-semibold border transition ${
        disabled
          ? "bg-white/5 text-slate-500 border-white/5 cursor-not-allowed"
          : "bg-white/10 hover:bg-white/20 text-white border-white/15"
      }`}
    >
      {!iconRight && icon}
      {label}
      {iconRight && icon}
    </button>
  );
}

function Typewriter({ text, speed = 55, forceDone, onDone, resetKey, live, className = "" }) {
  const [shown, setShown] = useState(0);
  const doneRef = useRef(false);
  const shownRef = useRef(0);

  useEffect(() => {
    shownRef.current = shown;
  }, [shown]);

  // Reset the cursor only when the logical line changes (new scene / new
  // sentence), NOT when the text prop grows because of a live stream delta.
  useEffect(() => {
    doneRef.current = false;
    setShown(0);
    shownRef.current = 0;
  }, [resetKey]);

  // Drive the cursor forward whenever the current text is longer than what
  // we've shown. This handles both the initial render and later appends
  // during a live stream.
  useEffect(() => {
    if (!text) {
      if (!doneRef.current) {
        doneRef.current = true;
        onDone && onDone();
      }
      return;
    }
    if (speed === 0) {
      setShown(text.length);
      shownRef.current = text.length;
      if (!doneRef.current) {
        doneRef.current = true;
        onDone && onDone();
      }
      return;
    }
    if (shownRef.current >= text.length) {
      if (!doneRef.current) {
        doneRef.current = true;
        onDone && onDone();
      }
      return;
    }
    // Text has grown past the cursor — we're not actually "done" anymore
    // even if we fired onDone earlier for a shorter prefix. Clear the
    // sentinel so the (shown === text.length) effect can fire again once
    // the typewriter catches up to the new length.
    doneRef.current = false;
    const id = setInterval(() => {
      shownRef.current += 1;
      const next = shownRef.current;
      setShown(next);
      if (next >= text.length) {
        clearInterval(id);
        // Don't mark done during a live stream — more text may still arrive.
        // onDone fires only if the parent signals forceDone or text stops
        // growing and matches shown; leaving the sentinel open lets the
        // effect re-trigger on the next delta.
      }
    }, speed);
    return () => clearInterval(id);
  }, [text, speed]);

  useEffect(() => {
    if (forceDone && text && shown < text.length) {
      setShown(text.length);
      shownRef.current = text.length;
      if (!doneRef.current) {
        doneRef.current = true;
        onDone && onDone();
      }
    }
  }, [forceDone, text, shown]);

  // When the cursor catches up to the full text AND no more is expected
  // (parent signals forceDone, or stream is no longer live), fire onDone.
  useEffect(() => {
    if (!text || doneRef.current) return;
    if (shown >= text.length && (forceDone || !live)) {
      doneRef.current = true;
      onDone && onDone();
    }
  }, [shown, text, forceDone, live]);

  const isDone = shown >= (text?.length || 0);
  return (
    <p className={className}>
      <span>{text ? text.slice(0, shown) : ""}</span>
      {!isDone && (
        <motion.span
          aria-hidden="true"
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 0.9, repeat: Infinity }}
          className="inline-block w-[0.4em] h-[1em] align-[-0.12em] ml-1 bg-indigo-300/90"
        />
      )}
    </p>
  );
}

function ChoicesOverlay({ choices, onPick, acting, pickedIdx }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35 }}
      className="absolute inset-0 z-[225] flex items-center justify-center bg-black/45 backdrop-blur-[2px] px-4"
    >
      <motion.div
        initial={{ scale: 0.98 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="w-full max-w-2xl space-y-3"
      >
        <div className="text-center text-xs tracking-widest uppercase text-indigo-300/90 pixel-font mb-4">
          {acting ? "命轮转动中…" : "此刻，你做出选择"}
        </div>
        {choices.map((c, idx) => {
          const isPicked = pickedIdx === idx;
          const dismissed = acting && !isPicked;
          return (
            <motion.button
              key={idx}
              disabled={acting}
              onClick={(e) => {
                e.stopPropagation();
                if (!acting) onPick && onPick(c, idx);
              }}
              initial={{ opacity: 0, y: 12 }}
              animate={
                dismissed
                  ? { opacity: 0, x: 40, scale: 0.96, transition: { duration: 0.25 } }
                  : isPicked
                  ? {
                      opacity: 1,
                      y: 0,
                      scale: [1, 1.03, 1],
                      transition: { duration: 0.35 },
                    }
                  : { opacity: 1, y: 0, transition: { delay: 0.2 * idx + 0.1, duration: 0.5 } }
              }
              whileTap={{ scale: 0.97 }}
              className={`group w-full text-left px-5 py-4 rounded-2xl border backdrop-blur transition text-slate-50 text-[16px] font-semibold relative overflow-hidden ${
                isPicked
                  ? "bg-indigo-500/40 border-indigo-300/80 shadow-[0_0_0_2px_rgba(129,140,248,0.5),0_12px_30px_-10px_rgba(99,102,241,0.8)]"
                  : "bg-white/8 hover:bg-white/15 border-white/15 hover:border-indigo-400/60"
              } ${acting ? "cursor-wait" : ""}`}
            >
              <span className="pixel-font text-indigo-300 mr-3 group-hover:text-indigo-200">
                {String.fromCharCode(65 + idx)}.
              </span>
              {c}
              {isPicked && acting && (
                <motion.span
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
                  className="inline-block ml-3 align-[-0.2em]"
                >
                  <RefreshCw size={14} className="text-indigo-200" />
                </motion.span>
              )}
              {/* Picked flash: a faint indigo wipe, then gone. Tells the
                  eye "this one got chosen" even before the overlay exits. */}
              {isPicked && (
                <motion.span
                  aria-hidden="true"
                  initial={{ x: "-100%", opacity: 0.6 }}
                  animate={{ x: "110%", opacity: 0 }}
                  transition={{ duration: 0.7, ease: "easeOut" }}
                  className="absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-transparent via-indigo-300/40 to-transparent pointer-events-none"
                />
              )}
            </motion.button>
          );
        })}
      </motion.div>
    </motion.div>
  );
}

function EpilogueOverlay({ run, onBack }) {
  // Prefer the per-run ending_text written by the LLM at the trigger turn
  // (M4c: free-form endings). Fall back to the world_bible blueprint only
  // when the slug matches a pre-declared ending — handles legacy runs.
  const endings = run?.world_bible?.possible_endings || [];
  const hit = endings.find((e) => e.slug === run?.ending_slug);
  const endingText =
    (run?.ending_text && run.ending_text.trim()) ||
    hit?.text ||
    "你的故事在此处落幕。";
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.8 }}
      className="absolute inset-0 z-[235] flex items-center justify-center bg-black/75 backdrop-blur px-6"
    >
      <motion.div
        initial={{ scale: 0.96, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        transition={{ duration: 0.7, ease: "easeOut", delay: 0.2 }}
        className="w-full max-w-xl rounded-3xl border border-white/15 bg-slate-950/85 p-8 md:p-10 text-center shadow-[0_30px_80px_-20px_rgba(0,0,0,0.9)]"
      >
        <div className="pixel-font text-[11px] tracking-[0.3em] uppercase text-indigo-300 mb-3">
          命途已定 · {run?.ending_slug || "unknown"}
        </div>
        <div className="text-xl md:text-2xl text-slate-50 leading-relaxed mb-6 font-semibold">
          {endingText}
        </div>
        <div className="flex items-center justify-center gap-6 text-sm text-slate-300 mb-8">
          <div>
            <div className="pixel-font text-[10px] text-slate-500 uppercase">回合</div>
            <div className="text-lg font-extrabold text-slate-100">{run?.turn_idx ?? 0}</div>
          </div>
          <div className="w-px h-10 bg-white/10" />
          <div>
            <div className="pixel-font text-[10px] text-slate-500 uppercase">分数</div>
            <div className="text-lg font-extrabold text-indigo-300">{run?.score ?? 0}</div>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onBack && onBack();
          }}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-500 hover:bg-indigo-400 transition text-white font-semibold text-sm"
        >
          <ArrowLeft size={15} /> 回到大厅
        </button>
      </motion.div>
    </motion.div>
  );
}

function WorldDrawer({ run, onClose }) {
  const world = run?.world_bible || {};
  const protagonist = world.protagonist || {};
  const npcs = world.npcs || [];
  const factions = world.factions || [];
  const state = run?.current_state || {};
  const codex = run?.codex || {};
  const relations = codex.relations || {};
  const keynotes = codex.keynotes || {};
  const secrets = codex.secrets || {};
  const genre = (run?.genre || world?.genre || "").toLowerCase();

  // Flatten every codex entry into a single list keyed by turn so the
  // timeline reads chronologically without the user having to fan out
  // three separate accordions.
  const timeline = useMemo(() => {
    const merged = [];
    const push = (bucket, kind) => {
      for (const [key, val] of Object.entries(bucket || {})) {
        merged.push({
          kind,
          key,
          note: val?.note || "",
          turn: Number(val?.turn || 0),
        });
      }
    };
    push(relations, "relation");
    push(keynotes, "keynote");
    push(secrets, "secret");
    // Latest → earliest: players open the drawer for "what just happened"
    // first; scroll down for backstory.
    merged.sort((a, b) => b.turn - a.turn);
    return merged;
  }, [codex]);

  const [tab, setTab] = useState("timeline");
  const tabs = [
    { id: "timeline", label: "时间线", count: timeline.length },
    { id: "cast", label: "众生", count: npcs.length + factions.length },
    { id: "hero", label: "主角", count: null },
  ];

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 z-[250] bg-black/70 backdrop-blur-md"
      />
      <motion.aside
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "tween", duration: 0.4, ease: "easeOut" }}
        className="absolute top-0 right-0 bottom-0 z-[251] w-full max-w-md bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 border-l border-white/10 overflow-y-auto text-slate-100"
      >
        <div className="sticky top-0 z-10 bg-slate-950/90 backdrop-blur border-b border-white/5">
          <div className="flex items-center justify-between px-6 py-4">
            <div className="pixel-font text-[10px] tracking-[0.25em] uppercase text-indigo-300/90">
              档案
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-white/10 text-slate-300 transition"
            >
              <CloseIcon size={16} />
            </button>
          </div>
          <div className="flex gap-1 px-4 pb-3">
            {tabs.map((t) => {
              const isActive = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`flex-1 px-3 py-1.5 rounded-xl text-[11px] font-bold pixel-font tracking-widest transition ${
                    isActive
                      ? "bg-white/10 text-white border border-white/20"
                      : "text-slate-400 hover:text-slate-200 border border-transparent"
                  }`}
                >
                  {t.label}
                  {typeof t.count === "number" && t.count > 0 && (
                    <span className="ml-1.5 text-[9px] text-slate-500">
                      {String(t.count).padStart(2, "0")}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        <div className="px-6 pt-6 pb-10 space-y-8">
          {tab === "timeline" && (
            <CodexTimeline entries={timeline} />
          )}
          {tab === "cast" && (
            <div className="space-y-8">
              {npcs.length > 0 ? (
                <NpcSection npcs={npcs} />
              ) : (
                <EmptyPane text="尚无 NPC 档案。" />
              )}
              {factions.length > 0 && <FactionSection factions={factions} />}
            </div>
          )}
          {tab === "hero" && (
            <HeroCard
              protagonist={protagonist}
              era={world.era}
              state={state}
              genre={genre}
            />
          )}
        </div>
      </motion.aside>
    </>
  );
}

const TIMELINE_KIND_META = {
  relation: { label: "羁绊", accent: "text-rose-300", dot: "bg-rose-400" },
  keynote:  { label: "线索", accent: "text-amber-300", dot: "bg-amber-400" },
  secret:   { label: "密事", accent: "text-violet-300", dot: "bg-violet-400" },
};

function CodexTimeline({ entries }) {
  if (!entries || entries.length === 0) {
    return (
      <EmptyPane text="目前还没有任何情报记录。随剧情推进，你的手札会在这里逐条展开。" />
    );
  }
  return (
    <section>
      <SectionHeader title="剧情手札" count={entries.length} />
      <ol className="relative pl-5 space-y-5 border-l border-white/10">
        {entries.map((e, i) => {
          const meta = TIMELINE_KIND_META[e.kind] || TIMELINE_KIND_META.keynote;
          return (
            <li key={`${e.kind}-${e.key}-${e.turn}-${i}`} className="relative">
              <span
                className={`absolute -left-[0.45rem] top-1.5 w-2 h-2 rounded-full ${meta.dot} ring-2 ring-slate-950`}
              />
              <div className="flex items-baseline gap-2 mb-1">
                <span className={`pixel-font text-[10px] tracking-widest ${meta.accent}`}>
                  T{String(e.turn).padStart(2, "0")}
                </span>
                <span className={`text-[10px] font-bold pixel-font tracking-widest ${meta.accent}`}>
                  {meta.label}
                </span>
                <span className="text-[13px] font-bold text-white truncate">
                  {e.key}
                </span>
              </div>
              {e.note && (
                <div className="text-[12px] text-slate-400 leading-relaxed">
                  {e.note}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function EmptyPane({ text }) {
  return (
    <div className="text-center text-[12px] text-slate-500 py-10 leading-relaxed">
      {text}
    </div>
  );
}

function HeroCard({ protagonist, era, state, genre }) {
  const name = protagonist.name || "无名之人";
  const origin = protagonist.origin || "";
  const goal = protagonist.goal || "";

  // Pick the state chip set by genre; fall back to location/mood for runs
  // whose genre we don't recognize (older rows, future additions).
  const cfg = GENRE_STATE_CONFIG[genre] || COMMON_STATE_FALLBACK;
  const chips = cfg
    .map((c) => ({ ...c, value: state?.[c.key] }))
    .filter((c) => c.value !== undefined && c.value !== null && c.value !== "");
  // If the genre-specific keys turned out empty (LLM didn't populate them
  // yet), still show location/mood so the panel isn't blank.
  const fallback =
    chips.length === 0
      ? COMMON_STATE_FALLBACK
          .map((c) => ({ ...c, value: state?.[c.key] }))
          .filter((c) => c.value !== undefined && c.value !== null && c.value !== "")
      : [];

  const rendered = chips.length ? chips : fallback;

  return (
    <div>
      <div className="text-[10px] tracking-[0.3em] uppercase text-slate-500 pixel-font mb-3">
        {era ? era.slice(0, 28) : "未定之世"}
      </div>
      <div className="text-[38px] leading-[1.05] font-black tracking-tight text-white mb-3">
        {name}
      </div>
      {origin && (
        <div className="text-[13px] text-slate-400 leading-relaxed mb-4 max-w-sm">
          {origin}
        </div>
      )}
      {goal && (
        <div className="text-[12px] text-indigo-200/90 leading-relaxed border-l-2 border-indigo-400/50 pl-3 py-0.5">
          {goal}
        </div>
      )}
      {rendered.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-2">
          {rendered.map((c) => (
            <StatusChip
              key={c.key}
              label={c.label}
              value={String(c.value)}
              tone={c.tone}
            />
          ))}
        </div>
      )}
    </div>
  );
}

const CHIP_TONES = {
  indigo:  "text-indigo-200 border-indigo-400/30 bg-indigo-500/10",
  rose:    "text-rose-200 border-rose-400/30 bg-rose-500/10",
  emerald: "text-emerald-200 border-emerald-400/30 bg-emerald-500/10",
  amber:   "text-amber-200 border-amber-400/30 bg-amber-500/10",
  violet:  "text-violet-200 border-violet-400/30 bg-violet-500/10",
  slate:   "text-slate-200 border-slate-400/30 bg-slate-500/10",
};

function StatusChip({ label, value, tone }) {
  const toneClass = CHIP_TONES[tone] || CHIP_TONES.indigo;
  return (
    <div
      className={`inline-flex items-baseline gap-2 px-3 py-1.5 rounded-full border text-[12px] ${toneClass}`}
    >
      <span className="text-[9px] tracking-[0.25em] uppercase opacity-70 pixel-font">
        {label}
      </span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function NpcSection({ npcs }) {
  const [openIdx, setOpenIdx] = useState(null);
  return (
    <section>
      <SectionHeader title="众生" count={npcs.length} />
      <div className="space-y-2">
        {npcs.map((n, i) => {
          const open = openIdx === i;
          const hasDetail = !!(n.stance || n.motive);
          return (
            <button
              key={i}
              type="button"
              onClick={() => hasDetail && setOpenIdx(open ? null : i)}
              className={`w-full text-left rounded-2xl border px-4 py-3 transition ${
                open
                  ? "bg-white/[0.06] border-white/15"
                  : "bg-white/[0.03] border-white/5 hover:bg-white/[0.05]"
              } ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="text-[17px] font-extrabold text-white truncate">
                    {n.name}
                  </span>
                  {n.role && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/8 text-slate-300 shrink-0">
                      {n.role}
                    </span>
                  )}
                </div>
                {hasDetail && (
                  <span
                    className={`text-slate-500 text-xs transition ${
                      open ? "rotate-180" : ""
                    }`}
                  >
                    ▾
                  </span>
                )}
              </div>
              <AnimatePresence initial={false}>
                {open && hasDetail && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                    className="overflow-hidden"
                  >
                    <div className="pt-2.5 text-[12px] text-slate-400 leading-relaxed space-y-1">
                      {n.stance && <div>{n.stance}</div>}
                      {n.motive && <div className="text-slate-500">{n.motive}</div>}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function FactionSection({ factions }) {
  const [openIdx, setOpenIdx] = useState(null);
  return (
    <section>
      <SectionHeader title="势力" count={factions.length} />
      <div className="space-y-2">
        {factions.map((f, i) => {
          const open = openIdx === i;
          const hasDetail = !!f.agenda;
          return (
            <button
              key={i}
              type="button"
              onClick={() => hasDetail && setOpenIdx(open ? null : i)}
              className={`w-full text-left rounded-2xl border px-4 py-3 transition ${
                open
                  ? "bg-white/[0.06] border-white/15"
                  : "bg-white/[0.03] border-white/5 hover:bg-white/[0.05]"
              } ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-[16px] font-extrabold text-white">
                  {f.name}
                </span>
                {hasDetail && (
                  <span
                    className={`text-slate-500 text-xs transition ${
                      open ? "rotate-180" : ""
                    }`}
                  >
                    ▾
                  </span>
                )}
              </div>
              <AnimatePresence initial={false}>
                {open && hasDetail && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                    className="overflow-hidden"
                  >
                    <div className="pt-2.5 text-[12px] text-slate-400 leading-relaxed">
                      {f.agenda}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function SectionHeader({ title, count }) {
  return (
    <div className="flex items-baseline justify-between mb-3">
      <h3 className="text-[22px] font-black tracking-tight text-white">{title}</h3>
      {typeof count === "number" && count > 0 && (
        <span className="pixel-font text-[10px] tracking-[0.25em] text-slate-500">
          {String(count).padStart(2, "0")}
        </span>
      )}
    </div>
  );
}

/* ── Shared meta-panel primitives ─────────────────────────────────────────
 * Gallery/Achievements/Leaderboard/History all live outside the pixel
 * theater view, but should still read as part of the same game product.
 * These helpers give the four surfaces a shared frame (scanlines + inset
 * border + pixel-font headers) without forcing the entire admin shell to
 * match.
 */

function MetaShell({ title, kicker, actions, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="space-y-4"
    >
      {(title || actions) && (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            {kicker && (
              <div className="pixel-font text-[10px] tracking-[0.3em] uppercase text-indigo-500 dark:text-indigo-300 mb-1">
                {kicker}
              </div>
            )}
            {title && (
              <h2 className="text-xl md:text-2xl font-extrabold tracking-tight text-slate-800 dark:text-white">
                {title}
              </h2>
            )}
          </div>
          {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
        </div>
      )}
      {children}
    </motion.div>
  );
}

function MetaCard({ children, className = "" }) {
  return (
    <div
      className={`relative overflow-hidden rounded-3xl border border-slate-200 dark:border-white/10 bg-white/70 dark:bg-slate-900/70 backdrop-blur ${className}`}
    >
      <div className="absolute inset-0 pixel-scanlines opacity-20 pointer-events-none" />
      <div className="relative">{children}</div>
    </div>
  );
}

function MetaEmpty({ text }) {
  return (
    <MetaCard>
      <div className="p-10 text-center text-sm text-slate-500 dark:text-slate-400">
        {text}
      </div>
    </MetaCard>
  );
}

const SORT_OPTIONS = [
  { id: "score",        label: "分数",   kind: "run"  },
  { id: "cg",           label: "收藏",   kind: "run"  },
  { id: "achievements", label: "成就",   kind: "user" },
  { id: "redeemed",     label: "兑奖",   kind: "user" },
  { id: "gifts_sent",   label: "赠送",   kind: "user" },
  { id: "gifts_got",    label: "受赠",   kind: "user" },
];

function LeaderboardView({ api }) {
  const [scope, setScope] = useState("all");
  const [sort, setSort] = useState("score");
  const [entries, setEntries] = useState([]);
  const [kind, setKind] = useState("run");
  const [loading, setLoading] = useState(true);

  const sortMeta = SORT_OPTIONS.find((s) => s.id === sort) || SORT_OPTIONS[0];
  const isUserBoard = sortMeta.kind === "user";

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .gameLeaderboard(scope, sort)
      .then((res) => {
        if (!alive) return;
        setEntries(res.data.entries || []);
        setKind(res.data.kind || "run");
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [scope, sort]);

  const toolbar = (
    <>
      {!isUserBoard && (
        <div className="flex items-center gap-1 p-1 rounded-xl bg-white/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
          {["all", "weekly"].map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                scope === s
                  ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                  : "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60"
              }`}
            >
              {s === "all" ? "总榜" : "周榜"}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1 p-1 rounded-xl bg-white/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 flex-wrap">
        {SORT_OPTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setSort(s.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
              sort === s.id
                ? "bg-indigo-500 text-white"
                : "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
    </>
  );

  return (
    <MetaShell kicker="排行" title="剧场榜单" actions={toolbar}>
      {loading ? (
        <MetaEmpty text="加载中…" />
      ) : entries.length === 0 ? (
        <MetaEmpty
          text={
            kind === "user"
              ? "暂无数据。完成成就、兑换、赠送后会出现在这里。"
              : "还没有人完成冒险。成为第一个登顶的人吧。"
          }
        />
      ) : kind === "user" ? (
        <div className="grid gap-3 md:grid-cols-2">
          {entries.map((e, idx) => (
            <UserBoardCard
              key={e.user_id}
              rank={idx + 1}
              entry={e}
              sort={sort}
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {entries.map((e, idx) => (
            <LeaderboardCard
              key={e.run_id}
              rank={idx + 1}
              entry={e}
              metric={sort === "cg" ? e.cg_count : e.score}
              metricLabel={sort === "cg" ? "CG" : "SCORE"}
            />
          ))}
        </div>
      )}
    </MetaShell>
  );
}

const USER_METRIC = {
  achievements: { field: "achievement_count", label: "成就",   fmt: (v) => String(v) },
  redeemed:     { field: "redeemed_usd",      label: "已兑换", fmt: (v) => `$${Number(v).toFixed(2)}` },
  gifts_sent:   { field: "gifts_sent",        label: "赠送",   fmt: (v) => String(v) },
  gifts_got:    { field: "gifts_got",         label: "受赠",   fmt: (v) => String(v) },
};

function UserBoardCard({ rank, entry, sort }) {
  const meta = USER_METRIC[sort] || USER_METRIC.achievements;
  const value = entry[meta.field];
  const isTop3 = rank <= 3;
  const rankTone = ["text-amber-400", "text-slate-300", "text-orange-300"][rank - 1];
  return (
    <MetaCard>
      <div className="flex items-center gap-4 p-4">
        <div
          className={`pixel-font text-2xl font-black shrink-0 ${
            isTop3 ? rankTone : "text-slate-400 dark:text-slate-500"
          }`}
        >
          #{String(rank).padStart(2, "0")}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-slate-800 dark:text-slate-100 truncate">
            {entry.display_name}
          </div>
          <div className="mt-0.5 flex items-center gap-2 flex-wrap text-[10px] text-slate-500 dark:text-slate-400 pixel-font tracking-widest">
            <span>成就 {entry.achievement_count}</span>
            <span>·</span>
            <span>兑 ${Number(entry.redeemed_usd || 0).toFixed(2)}</span>
            <span>·</span>
            <span>赠 {entry.gifts_sent}</span>
            <span>·</span>
            <span>CG {entry.cg_count}</span>
          </div>
        </div>
        <div className="text-right shrink-0">
          <div
            className={`text-xl font-black pixel-font ${
              isTop3 ? rankTone : "text-indigo-600 dark:text-indigo-300"
            }`}
          >
            {meta.fmt(value)}
          </div>
          <div className="text-[9px] text-slate-400 pixel-font uppercase tracking-widest">
            {meta.label}
          </div>
        </div>
      </div>
    </MetaCard>
  );
}

function LeaderboardCard({ rank, entry, metric, metricLabel }) {
  const genreLabel = GENRE_LABELS[entry.genre]?.name || entry.genre || "未定";
  const isTop3 = rank <= 3;
  const rankTone = ["text-amber-400", "text-slate-300", "text-orange-300"][rank - 1];
  return (
    <MetaCard>
      <div className="flex items-stretch gap-3 p-4">
        <div className="shrink-0 flex items-center justify-center">
          <div
            className={`pixel-font text-2xl font-black ${
              isTop3 ? rankTone : "text-slate-400 dark:text-slate-500"
            }`}
          >
            #{String(rank).padStart(2, "0")}
          </div>
        </div>
        {entry.cover_url ? (
          <img
            src={entry.cover_url}
            alt=""
            loading="lazy"
            className="w-16 h-16 rounded-lg object-cover pixel-canvas shrink-0 border border-white/10"
          />
        ) : (
          <div className="w-16 h-16 rounded-lg bg-gradient-to-br from-indigo-500/20 to-purple-500/20 shrink-0 flex items-center justify-center text-slate-400">
            <ImageIcon size={18} />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="font-bold text-slate-800 dark:text-slate-100 truncate">
            {entry.display_name}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-300 pixel-font tracking-widest">
              {genreLabel}
            </span>
            {entry.ending_slug && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300 truncate max-w-[9rem]">
                {entry.ending_slug}
              </span>
            )}
            <span className="text-[10px] text-slate-400">
              {entry.turns} 回 · CG {entry.cg_count}
            </span>
          </div>
        </div>
        <div className="text-right shrink-0 flex flex-col justify-center">
          <div
            className={`text-xl font-black pixel-font ${
              isTop3 ? rankTone : "text-indigo-600 dark:text-indigo-300"
            }`}
          >
            {metric}
          </div>
          <div className="text-[9px] text-slate-400 pixel-font uppercase tracking-widest">
            {metricLabel}
          </div>
        </div>
      </div>
    </MetaCard>
  );
}

const HISTORY_STATUS_META = {
  active:    { label: "进行中", tone: "text-emerald-500 border-emerald-400/50 bg-emerald-500/10" },
  ended:     { label: "已完成", tone: "text-indigo-500 border-indigo-400/50 bg-indigo-500/10" },
  abandoned: { label: "已放弃", tone: "text-slate-500 border-slate-400/40 bg-slate-500/10" },
};

function HistoryView({ api }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.gameHistory();
        if (!cancelled) setEntries(data.runs || data.entries || []);
      } catch {
        /* silent */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const grouped = useMemo(() => {
    return {
      active: entries.filter((e) => e.status === "running" || e.status === "generating"),
      ended: entries.filter((e) => e.status === "ended"),
      abandoned: entries.filter((e) => e.status === "abandoned"),
    };
  }, [entries]);

  return (
    <MetaShell kicker="历程" title="我的冒险">
      {loading ? (
        <MetaEmpty text="加载中…" />
      ) : entries.length === 0 ? (
        <MetaEmpty text="还没有冒险记录。去开启第一次吧。" />
      ) : (
        <div className="space-y-6">
          {["active", "ended", "abandoned"].map((key) =>
            grouped[key].length ? (
              <section key={key}>
                <div className="flex items-baseline justify-between mb-3">
                  <h3 className="pixel-font text-[11px] tracking-[0.3em] uppercase text-slate-500 dark:text-slate-400">
                    {HISTORY_STATUS_META[key].label}
                  </h3>
                  <span className="pixel-font text-[10px] text-slate-400">
                    {String(grouped[key].length).padStart(2, "0")}
                  </span>
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {grouped[key].map((e) => (
                    <HistoryCard key={e.id} run={e} statusKey={key} />
                  ))}
                </div>
              </section>
            ) : null
          )}
        </div>
      )}
    </MetaShell>
  );
}

function HistoryCard({ run, statusKey }) {
  const meta = HISTORY_STATUS_META[statusKey] || HISTORY_STATUS_META.ended;
  const genreLabel = GENRE_LABELS[run.genre]?.name || run.genre || "未定";
  return (
    <MetaCard>
      <div className="p-4 flex items-start gap-3">
        {run.cover_url ? (
          <img
            src={run.cover_url}
            alt=""
            loading="lazy"
            className="w-14 h-14 rounded-lg object-cover pixel-canvas border border-white/10 shrink-0"
          />
        ) : (
          <div className="w-14 h-14 rounded-lg bg-gradient-to-br from-slate-200 to-slate-300 dark:from-slate-700 dark:to-slate-800 shrink-0 flex items-center justify-center text-slate-400">
            <ImageIcon size={16} />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-slate-800 dark:text-slate-100 text-sm">
              Run #{run.id}
            </span>
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded border font-bold pixel-font tracking-widest ${meta.tone}`}
            >
              {meta.label}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-300 pixel-font tracking-widest">
              {genreLabel}
            </span>
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 truncate">
            {run.started_at} · {run.turn_idx} 回合
            {run.ending_slug ? ` · ${run.ending_slug}` : ""}
          </div>
        </div>
        {statusKey === "ended" && (
          <div className="text-right">
            <div className="text-sm font-black pixel-font text-indigo-600 dark:text-indigo-300">
              {run.score || 0}
            </div>
            <div className="text-[9px] text-slate-400 pixel-font uppercase tracking-widest">
              SCORE
            </div>
          </div>
        )}
      </div>
    </MetaCard>
  );
}

/* ── GalleryView ─────────────────────────────────────────────────────────── */

const GALLERY_GENRE_FILTERS = [
  { slug: "", label: "全部" },
  ...Object.entries(GENRE_LABELS).map(([slug, g]) => ({ slug, label: g.name })),
];

const RARITY_STYLE = {
  common: {
    label: "常",
    ring: "border-slate-300 dark:border-slate-600",
    glow: "",
    chip: "bg-slate-500/80",
  },
  rare: {
    label: "珍",
    ring: "border-indigo-400/60",
    glow: "shadow-[0_0_24px_-4px_rgba(129,140,248,0.45)]",
    chip: "bg-indigo-500/80",
  },
  epic: {
    label: "秘",
    ring: "border-violet-400/70",
    glow: "shadow-[0_0_30px_-2px_rgba(167,139,250,0.55)]",
    chip: "bg-violet-500/80",
  },
};

function genreName(slug) {
  return GENRE_LABELS[slug]?.name || slug || "未定";
}

function rarityMeta(rarity) {
  return RARITY_STYLE[rarity] || RARITY_STYLE.common;
}

function cgCode(sceneId) {
  const n = Number(sceneId || 0);
  return `CG-${String(n).padStart(6, "0")}`;
}

function originLabel(item) {
  if (!item) return "";
  if (item.source === "origin") return "原创入藏";
  if (item.source === "gift") return "赠送获得";
  if (item.source === "trade") return "交易换入";
  if (item.source === "marketplace") return "市场购入";
  return item.source || "入藏";
}

function CollectionStat({ label, value, icon }) {
  return (
    <div className="min-w-[7rem] rounded-2xl border border-slate-200/80 dark:border-white/10 bg-white/75 dark:bg-slate-950/40 px-4 py-3 shadow-sm">
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-400 pixel-font">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-2xl font-black tracking-tight text-slate-900 dark:text-white">
        {value}
      </div>
    </div>
  );
}

function SegmentTabs({ items, value, onChange }) {
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
      {items.map((it) => (
        <button
          key={it.key || it.slug}
          onClick={() => onChange(it.key ?? it.slug)}
          className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold transition ${
            value === (it.key ?? it.slug)
              ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow"
              : "bg-white/70 dark:bg-slate-900/60 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

function FlashNotice({ flash }) {
  if (!flash) return null;
  return (
    <div
      className={`rounded-2xl px-4 py-3 text-sm font-semibold border ${
        flash.tone === "success"
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-400/40"
          : "bg-red-500/10 text-red-700 dark:text-red-300 border-red-400/40"
      }`}
    >
      {flash.text}
    </div>
  );
}

function CgThumbStack({ items = [], size = "md" }) {
  const dims = size === "lg" ? "w-14 h-14" : "w-11 h-11";
  const visible = items.slice(0, 4);
  return (
    <div className="flex -space-x-2">
      {visible.map((s, i) => (
        <img
          key={s.id || s.scene_id || i}
          src={s.image_url}
          alt=""
          className={`${dims} rounded-xl object-cover border-2 border-white dark:border-slate-950 pixel-canvas bg-slate-200 dark:bg-slate-800`}
          style={{ zIndex: visible.length - i }}
          loading="lazy"
        />
      ))}
      {items.length > visible.length && (
        <div className={`${dims} rounded-xl border-2 border-white dark:border-slate-950 bg-slate-900 text-white flex items-center justify-center text-[11px] font-bold`}>
          +{items.length - visible.length}
        </div>
      )}
    </div>
  );
}

function CgGalleryCard({ item, featured = false, onClick }) {
  const style = rarityMeta(item.rarity);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative overflow-hidden rounded-2xl border bg-slate-100 dark:bg-slate-900 focus:outline-none transition duration-300 hover:-translate-y-0.5 hover:shadow-xl ${style.ring} ${style.glow} ${
        featured ? "aspect-[16/10] md:col-span-2 md:row-span-2" : "aspect-[4/3]"
      }`}
    >
      <img
        src={item.image_url}
        alt=""
        loading="lazy"
        className="absolute inset-0 w-full h-full object-cover pixel-canvas transition duration-500 group-hover:scale-[1.045]"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/15 to-black/0 opacity-95" />
      <div className="absolute inset-0 pixel-scanlines opacity-20 pointer-events-none" />
      <div className="absolute top-3 left-3 flex items-center gap-1.5">
        <span className={`px-2 py-1 rounded-lg text-[10px] text-white font-black pixel-font tracking-widest ${style.chip}`}>
          {style.label}
        </span>
        {item.is_keynote ? (
          <span className="px-2 py-1 rounded-lg bg-amber-500/90 text-[10px] text-white font-black pixel-font tracking-widest">
            KEY
          </span>
        ) : null}
      </div>
      <div className="absolute bottom-0 inset-x-0 p-3 text-left">
        <div className="text-white font-black tracking-tight">
          {cgCode(item.scene_id)}
        </div>
        <div className="mt-1 flex items-center gap-1.5 flex-wrap text-[10px] text-white/75">
          <span>{genreName(item.genre)}</span>
          <span>·</span>
          <span>第 {item.turn_idx} 回</span>
          <span>·</span>
          <span>{originLabel(item)}</span>
        </div>
      </div>
      <div className="absolute right-3 bottom-3 opacity-0 group-hover:opacity-100 transition">
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/90 text-slate-900 text-[11px] font-bold shadow">
          <Eye size={13} /> 查看
        </span>
      </div>
    </button>
  );
}

function DetailRow({ label, value }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/5 py-2.5">
      <span className="text-[10px] uppercase tracking-widest text-slate-500 pixel-font">
        {label}
      </span>
      <span className="text-sm text-slate-200 text-right leading-relaxed">
        {value}
      </span>
    </div>
  );
}

function GiftPane({ api, scene, onDone, onCancel }) {
  const [query, setQuery] = useState("");
  const [resolved, setResolved] = useState(null); // {user_id, display_name, student_id}
  const [matches, setMatches] = useState(null); // null | list of candidates
  const [lookupErr, setLookupErr] = useState(null);
  const [looking, setLooking] = useState(false);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState(null);

  async function lookup() {
    const q = query.trim();
    if (!q) return;
    setLooking(true);
    setLookupErr(null);
    setMatches(null);
    setResolved(null);
    try {
      const { data } = await api.gameLookupByName(q);
      const list = data.matches || [];
      if (list.length === 0) {
        setLookupErr("找不到该用户");
      } else if (list.length === 1) {
        setResolved(list[0]);
      } else {
        setMatches(list);
      }
    } catch {
      setLookupErr("查找失败");
    } finally {
      setLooking(false);
    }
  }

  async function confirm() {
    if (!resolved || sending) return;
    setSending(true);
    setSendErr(null);
    try {
      await api.gameSendGift({
        scene_id: scene.scene_id,
        to_user_id: resolved.user_id,
        message: message.trim() || undefined,
      });
      onDone && onDone({ ok: true, toLabel: resolved.display_name });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "object" ? detail.code : null;
      const msg = {
        self_gift: "不能赠送给自己",
        not_owned: "你已不再拥有这张 CG",
        not_transferable: "继无之宝不可赠送",
        already_owned: "对方已经拥有这张 CG",
        rate_limited: "今日赠送已达上限（20 次）",
        message_too_long: "留言过长（最多 140 字）",
      }[code] || "赠送失败";
      setSendErr(msg);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="rounded-2xl border border-indigo-400/40 bg-indigo-500/5 p-4 space-y-3">
      <div className="pixel-font text-[10px] tracking-[0.3em] uppercase text-indigo-300">
        赠送此 CG
      </div>
      {!resolved && !matches ? (
        <>
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") lookup();
              }}
              placeholder="输入昵称搜索"
              className="flex-1 px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-400"
            />
            <button
              type="button"
              onClick={lookup}
              disabled={looking || !query.trim()}
              className="px-3 py-2 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white text-xs font-bold disabled:opacity-50 transition"
            >
              {looking ? "查找中…" : "查找"}
            </button>
          </div>
          {lookupErr && (
            <div className="text-[11px] text-red-300">{lookupErr}</div>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onCancel}
              className="text-[11px] text-slate-400 hover:text-slate-200"
            >
              取消
            </button>
          </div>
        </>
      ) : matches ? (
        <>
          <div className="text-xs text-slate-400 mb-1">找到 {matches.length} 个用户，点击选择：</div>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {matches.map((m) => (
              <button
                key={m.user_id}
                type="button"
                onClick={() => { setResolved(m); setMatches(null); }}
                className="w-full text-left px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-indigo-400/50 transition"
              >
                <span className="text-sm font-bold text-slate-100">{m.display_name}</span>
                <span className="text-[10px] text-slate-500 ml-2">{m.student_id}</span>
              </button>
            ))}
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => { setMatches(null); setQuery(""); }}
              className="text-[11px] text-slate-400 hover:text-slate-200"
            >
              重新搜索
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center gap-2 text-sm text-slate-200">
            <span>赠送给</span>
            <span className="font-bold">{resolved.display_name}</span>
            <span className="text-[11px] text-slate-400">
              #{resolved.student_id}
            </span>
            <button
              type="button"
              onClick={() => {
                setResolved(null);
                setQuery("");
              }}
              className="ml-auto text-[11px] text-indigo-300 hover:text-indigo-200"
            >
              换一个
            </button>
          </div>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="附一句留言（可选，≤140 字）"
            maxLength={140}
            rows={2}
            className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-400 resize-none"
          />
          {sendErr && (
            <div className="text-[11px] text-red-300">{sendErr}</div>
          )}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onCancel}
              className="px-3 py-1.5 rounded-lg text-[11px] text-slate-400 hover:text-slate-200"
            >
              取消
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={sending}
              className="px-4 py-1.5 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white text-xs font-bold disabled:opacity-60 disabled:cursor-wait transition"
            >
              {sending ? "送出中…" : "确认赠送"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/* ─── TradeComposer: fullscreen modal for creating a trade offer ─── */
function TradeComposer({ api, seedScene, onClose, onCreated }) {
  const [myCgs, setMyCgs] = useState([]);
  const [myLoading, setMyLoading] = useState(true);
  const [offered, setOffered] = useState([seedScene.scene_id]);

  const [query, setQuery] = useState("");
  const [recipient, setRecipient] = useState(null);
  const [matches, setMatches] = useState(null);
  const [lookupErr, setLookupErr] = useState(null);
  const [looking, setLooking] = useState(false);
  const [theirCgs, setTheirCgs] = useState([]);
  const [theirLoading, setTheirLoading] = useState(false);
  const [wanted, setWanted] = useState([]);

  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState(null);

  /* load my gallery */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setMyLoading(true);
      try {
        const { data } = await api.gameMyGallery();
        if (!cancelled) setMyCgs(data.items || []);
      } catch { /* */ } finally {
        if (!cancelled) setMyLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  async function lookup() {
    const q = query.trim();
    if (!q) return;
    setLooking(true);
    setLookupErr(null);
    setMatches(null);
    setRecipient(null);
    setTheirCgs([]);
    setWanted([]);
    try {
      const { data } = await api.gameLookupByName(q);
      const list = data.matches || [];
      if (list.length === 0) {
        setLookupErr("找不到该用户");
      } else if (list.length === 1) {
        selectRecipient(list[0]);
      } else {
        setMatches(list);
      }
    } catch {
      setLookupErr("查找失败");
    } finally {
      setLooking(false);
    }
  }

  async function selectRecipient(user) {
    setRecipient(user);
    setMatches(null);
    setTheirLoading(true);
    try {
      const { data: g } = await api.gamePublicGallery(user.user_id);
      setTheirCgs(g.items || []);
    } catch { /* */ } finally {
      setTheirLoading(false);
    }
  }

  function toggle(list, setter, id, max) {
    setter((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= max) return prev;
      return [...prev, id];
    });
  }

  async function submit() {
    if (!recipient || offered.length === 0 || wanted.length === 0 || sending) return;
    setSending(true);
    setSendErr(null);
    try {
      const { data } = await api.gameCreateTrade({
        to_user_id: recipient.user_id,
        offered_scene_ids: offered,
        wanted_scene_ids: wanted,
        message: message.trim() || undefined,
      });
      onCreated && onCreated(data);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "object" ? detail.code : null;
      const msg = {
        self_trade: "不能与自己交易",
        not_owned: "你已不再拥有某张 CG",
        not_transferable: "继无之宝不可交易",
        already_owned: "对方已拥有你出价的 CG",
        max_offered: "最多出价 5 张 CG",
        max_wanted: "最多求购 5 张 CG",
        message_too_long: "留言过长（最多 140 字）",
      }[code] || "交易创建失败";
      setSendErr(msg);
    } finally {
      setSending(false);
    }
  }

  const canSubmit = recipient && offered.length > 0 && wanted.length > 0 && !sending;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/85 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.92, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.92, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-2xl max-h-[85vh] rounded-3xl bg-slate-950 border border-white/10 shadow-2xl overflow-hidden flex flex-col"
      >
        {/* header */}
        <div className="shrink-0 flex items-center justify-between px-5 py-3 border-b border-white/10">
          <div className="pixel-font text-[10px] tracking-[0.3em] uppercase text-emerald-300">
            发起交易
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20 transition"
          >
            <CloseIcon size={13} />
          </button>
        </div>

        {/* body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* my CGs */}
          <section>
            <div className="text-xs font-bold text-slate-300 mb-2">
              我出价的 CG <span className="text-slate-500">（最多 5 张）</span>
            </div>
            {myLoading ? (
              <div className="text-xs text-slate-500 py-4">加载中…</div>
            ) : myCgs.length === 0 ? (
              <div className="text-xs text-slate-500 py-4">暂无 CG 收藏</div>
            ) : (
              <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
                {myCgs.map((it) => {
                  const sel = offered.includes(it.scene_id);
                  return (
                    <button
                      key={it.ownership_id}
                      type="button"
                      onClick={() => toggle(offered, setOffered, it.scene_id, 5)}
                      className={`relative rounded-xl overflow-hidden aspect-[4/3] border-2 transition ${
                        sel
                          ? "border-emerald-400 ring-2 ring-emerald-400/40"
                          : "border-transparent opacity-60 hover:opacity-100"
                      }`}
                    >
                      <img
                        src={it.image_url}
                        alt=""
                        className="w-full h-full object-cover pixel-canvas"
                        loading="lazy"
                      />
                      {sel && (
                        <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center text-[10px] font-bold">
                          ✓
                        </div>
                      )}
                      {it.scene_id === seedScene.scene_id && (
                        <div className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-amber-500/90 text-[9px] font-bold text-white pixel-font">
                          当前
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {/* recipient lookup */}
          <section>
            <div className="text-xs font-bold text-slate-300 mb-2">交易对象</div>
            {!recipient && !matches ? (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") lookup(); }}
                  placeholder="输入昵称搜索"
                  className="flex-1 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-emerald-400"
                />
                <button
                  type="button"
                  onClick={lookup}
                  disabled={looking || !query.trim()}
                  className="px-3 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-bold disabled:opacity-50 transition"
                >
                  {looking ? "查找中…" : "查找"}
                </button>
              </div>
            ) : matches ? (
              <>
                <div className="text-xs text-slate-400 mb-1">找到 {matches.length} 个用户，点击选择：</div>
                <div className="space-y-1.5 max-h-32 overflow-y-auto">
                  {matches.map((m) => (
                    <button
                      key={m.user_id}
                      type="button"
                      onClick={() => selectRecipient(m)}
                      className="w-full text-left px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-emerald-400/50 transition"
                    >
                      <span className="text-sm font-bold text-slate-100">{m.display_name}</span>
                      <span className="text-[10px] text-slate-500 ml-2">{m.student_id}</span>
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => { setMatches(null); setQuery(""); }}
                  className="text-xs text-slate-400 hover:text-slate-200 mt-1"
                >
                  重新搜索
                </button>
              </>
            ) : (
              <div className="flex items-center gap-3">
                <div className="flex-1 px-3 py-2 rounded-lg bg-slate-900 border border-emerald-500/40">
                  <div className="text-sm font-bold text-slate-100">{recipient.display_name}</div>
                  <div className="text-[10px] text-slate-400">{recipient.student_id}</div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setRecipient(null);
                    setTheirCgs([]);
                    setWanted([]);
                    setQuery("");
                  }}
                  className="text-xs text-slate-400 hover:text-slate-200 transition"
                >
                  更换
                </button>
              </div>
            )}
            {lookupErr && (
              <div className="text-xs text-red-400 mt-1">{lookupErr}</div>
            )}
          </section>

          {/* their CGs */}
          {recipient && (
            <section>
              <div className="text-xs font-bold text-slate-300 mb-2">
                我想要的 CG <span className="text-slate-500">（最多 5 张）</span>
              </div>
              {theirLoading ? (
                <div className="text-xs text-slate-500 py-4">加载对方画廊…</div>
              ) : theirCgs.length === 0 ? (
                <div className="text-xs text-slate-500 py-4">对方暂无 CG 收藏</div>
              ) : (
                <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
                  {theirCgs.map((it) => {
                    const sel = wanted.includes(it.scene_id);
                    return (
                      <button
                        key={it.ownership_id}
                        type="button"
                        onClick={() => toggle(wanted, setWanted, it.scene_id, 5)}
                        className={`relative rounded-xl overflow-hidden aspect-[4/3] border-2 transition ${
                          sel
                            ? "border-indigo-400 ring-2 ring-indigo-400/40"
                            : "border-transparent opacity-60 hover:opacity-100"
                        }`}
                      >
                        <img
                          src={it.image_url}
                          alt=""
                          className="w-full h-full object-cover pixel-canvas"
                          loading="lazy"
                        />
                        {sel && (
                          <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-indigo-500 text-white flex items-center justify-center text-[10px] font-bold">
                            ✓
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {/* message */}
          {recipient && (
            <section>
              <div className="text-xs font-bold text-slate-300 mb-2">留言 <span className="text-slate-500">（可选）</span></div>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value.slice(0, 140))}
                placeholder="给对方留句话…"
                rows={2}
                className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-emerald-400 resize-none"
              />
              <div className="text-[10px] text-slate-500 text-right mt-0.5">{message.length}/140</div>
            </section>
          )}

          {sendErr && (
            <div className="rounded-lg bg-red-500/15 border border-red-400/30 px-3 py-2 text-xs text-red-300">
              {sendErr}
            </div>
          )}
        </div>

        {/* footer */}
        <div className="shrink-0 flex items-center justify-between px-5 py-3 border-t border-white/10">
          <div className="text-[10px] text-slate-500">
            {offered.length} 出价 · {wanted.length} 求购
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 transition"
            >
              取消
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit}
              className="px-4 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              {sending ? "提交中…" : "发出交易"}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function GalleryView({ api }) {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState({ total: 0, per_genre: {} });
  const [genre, setGenre] = useState("");
  const [rarity, setRarity] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [giftOpen, setGiftOpen] = useState(false);
  const [giftFlash, setGiftFlash] = useState(null);
  const [tradeOpen, setTradeOpen] = useState(false);
  const [listPrice, setListPrice] = useState("");
  const [listing, setListing] = useState(false);

  async function handleList() {
    const price = parseFloat(listPrice);
    if (!price || price <= 0 || !selected || listing) return;
    setListing(true);
    try {
      await api.gameCreateListing({ scene_id: selected.scene_id, price_usd: price });
      setGiftFlash({ tone: "success", text: `已上架 · $${price.toFixed(2)}` });
      setTimeout(() => setGiftFlash(null), 3000);
      setListPrice("");
      setSelected(null);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "object" ? detail.code : null;
      setGiftFlash({ tone: "error", text: {
        pioneer_locked: "开荒 CG 不可上架",
        not_owned: "你已不再拥有此 CG",
        bad_price: "价格无效",
      }[code] || "上架失败" });
      setTimeout(() => setGiftFlash(null), 3000);
    } finally {
      setListing(false);
    }
  }

  async function refresh() {
    setLoading(true);
    try {
      const { data } = await api.gameMyGallery(genre || undefined);
      setItems(data.items || []);
      setSummary(data.summary || { total: 0, per_genre: {} });
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.gameMyGallery(genre || undefined);
        if (!cancelled) {
          setItems(data.items || []);
          setSummary(data.summary || { total: 0, per_genre: {} });
        }
      } catch { /* silent */ } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [genre]);

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((it) => {
      if (rarity && (it.rarity || "common") !== rarity) return false;
      if (!q) return true;
      const hay = [
        cgCode(it.scene_id),
        genreName(it.genre),
        it.source,
        it.origin_display_name,
        it.origin_student_id,
        it.ending_slug,
        it.run_id,
      ].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }, [items, query, rarity]);

  const featured = visibleItems[0] || null;
  const rest = featured ? visibleItems.slice(1) : [];
  const rareCount = items.filter((it) => (it.rarity || "common") !== "common" || it.is_keynote).length;

  const summaryChip = (
    <div className="flex items-center gap-2 flex-wrap">
      <CollectionStat label="藏品" value={summary.total || 0} icon={<ImageIcon size={12} />} />
      <CollectionStat label="珍藏" value={rareCount} icon={<Medal size={12} />} />
      <CollectionStat label="题材" value={Object.keys(summary.per_genre || {}).length} icon={<Layers3 size={12} />} />
    </div>
  );

  return (
    <MetaShell kicker="画廊" title="我的收藏" actions={summaryChip}>
      <MetaCard className="p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <SegmentTabs
            items={GALLERY_GENRE_FILTERS}
            value={genre}
            onChange={setGenre}
          />
          <div className="flex items-center gap-2">
            <div className="relative min-w-[13rem]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索编号、题材、来源"
                className="w-full rounded-full border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-950/70 pl-9 pr-3 py-2 text-xs text-slate-700 dark:text-slate-200 outline-none focus:border-indigo-400"
              />
            </div>
            <select
              value={rarity}
              onChange={(e) => setRarity(e.target.value)}
              className="rounded-full border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-950/70 px-3 py-2 text-xs text-slate-700 dark:text-slate-200 outline-none focus:border-indigo-400"
            >
              <option value="">全部稀有度</option>
              <option value="common">普通</option>
              <option value="rare">珍藏</option>
              <option value="epic">秘藏</option>
            </select>
          </div>
        </div>
      </MetaCard>

      <FlashNotice flash={giftFlash} />

      {loading ? (
        <MetaEmpty text="加载中…" />
      ) : items.length === 0 ? (
        <MetaEmpty
          text={genre ? "这个题材还没有入藏画面。" : "还没有入藏的画面。完成一段冒险后，关键场景会自动收录。"}
        />
      ) : visibleItems.length === 0 ? (
        <MetaEmpty text="没有符合筛选条件的 CG。" />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 auto-rows-fr">
          {featured && (
            <CgGalleryCard
              item={featured}
              featured
              onClick={() => setSelected(featured)}
            />
          )}
          {rest.map((it) => (
            <CgGalleryCard
              key={it.ownership_id}
              item={it}
              onClick={() => setSelected(it)}
            />
          ))}
        </div>
      )}

      <AnimatePresence>
        {selected && (
          <motion.div
            key="lightbox"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[110] flex items-center justify-center bg-black/85 backdrop-blur-md p-4"
            onClick={() => {
              setSelected(null);
              setGiftOpen(false);
            }}
          >
            <motion.div
              initial={{ scale: 0.96, opacity: 0, y: 18 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.96, opacity: 0, y: 18 }}
              className="relative w-full max-w-6xl max-h-[88vh] overflow-hidden rounded-3xl bg-slate-950 text-slate-100 shadow-2xl border border-white/10 grid lg:grid-cols-[minmax(0,1.45fr)_25rem]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relative min-h-[18rem] bg-black">
                <img
                  src={selected.image_url}
                  alt=""
                  className="absolute inset-0 w-full h-full object-contain pixel-canvas"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-black/20 pointer-events-none" />
                <div className="absolute inset-0 pixel-scanlines opacity-20 pointer-events-none" />
                <div className="absolute left-5 bottom-5">
                  <div className="pixel-font text-[10px] tracking-[0.35em] text-white/60 uppercase">
                    {cgCode(selected.scene_id)}
                  </div>
                  <div className="mt-1 text-2xl md:text-4xl font-black text-white tracking-tight">
                    第 {selected.turn_idx} 回
                  </div>
                </div>
              </div>
              <div className="max-h-[88vh] overflow-y-auto p-5 md:p-6 space-y-5 border-l border-white/10">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] px-2 py-1 rounded-lg bg-indigo-500/20 border border-indigo-400/30 text-indigo-200 font-bold pixel-font tracking-widest">
                    {genreName(selected.genre)}
                  </span>
                  <span className="text-[10px] px-2 py-1 rounded-lg bg-amber-500/20 border border-amber-400/30 text-amber-200 font-bold pixel-font tracking-widest">
                    {originLabel(selected)}
                  </span>
                  <span className="text-[10px] px-2 py-1 rounded-lg bg-violet-500/20 border border-violet-400/30 text-violet-200 font-bold pixel-font tracking-widest">
                    {rarityMeta(selected.rarity).label}
                  </span>
                </div>

                <div>
                  <div className="text-2xl font-black tracking-tight text-white">
                    藏品详情
                  </div>
                  <div className="mt-1 text-sm text-slate-500">
                    {selected.is_keynote ? "关键画面" : "场景画面"} · Run #{selected.run_id}
                  </div>
                </div>

                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4">
                  <DetailRow label="编号" value={cgCode(selected.scene_id)} />
                  <DetailRow label="题材" value={genreName(selected.genre)} />
                  <DetailRow label="来源" value={originLabel(selected)} />
                  <DetailRow label="原创者" value={selected.origin_display_name || selected.origin_student_id} />
                  <DetailRow label="入藏" value={selected.acquired_at} />
                  <DetailRow label="结局" value={selected.ending_slug} />
                </div>

                {/* Gift controls — only available for CGs the user owns
                    (GalleryView's /gallery/me feed) and not pioneer-locked. */}
                {(() => {
                  const isPioneer =
                    selected.source === "origin" && !!selected.is_keynote;
                  if (isPioneer) {
                    return (
                      <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-[11px] text-amber-200 pixel-font tracking-widest">
                        开荒关键画面 · 暂不可赠送 / 交易 / 上架
                      </div>
                    );
                  }
                  return (
                    <div className="pt-2">
                      {giftOpen ? (
                        <GiftPane
                          api={api}
                          scene={selected}
                          onDone={(result) => {
                            setGiftOpen(false);
                            if (result?.ok) {
                              setSelected(null);
                              setGiftFlash({
                                tone: "success",
                                text: `已赠送给 ${result.toLabel}`,
                              });
                              setTimeout(() => setGiftFlash(null), 3200);
                              refresh();
                            }
                          }}
                          onCancel={() => setGiftOpen(false)}
                        />
                      ) : (
                        <div className="space-y-2">
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => setGiftOpen(true)}
                              className="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-bold bg-indigo-500 hover:bg-indigo-400 text-white transition"
                            >
                              <Gift size={15} /> 赠送
                            </button>
                            <button
                              type="button"
                              onClick={() => setTradeOpen(true)}
                              className="flex-1 px-3 py-2 rounded-xl text-sm font-bold bg-emerald-500 hover:bg-emerald-400 text-white transition inline-flex items-center justify-center gap-1.5"
                            >
                              <ArrowLeftRight size={14} /> 交易
                            </button>
                          </div>
                          <div className="flex gap-1.5">
                            <input
                              type="number"
                              min="0.01"
                              step="0.01"
                              value={listPrice}
                              onChange={(e) => setListPrice(e.target.value)}
                              placeholder="定价 USD"
                              className="flex-1 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-amber-400"
                            />
                            <button
                              type="button"
                              onClick={handleList}
                              disabled={listing || !listPrice || parseFloat(listPrice) <= 0}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-500 hover:bg-amber-400 text-white transition disabled:opacity-50"
                            >
                              <Tag size={13} /> {listing ? "…" : "上架"}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
              <button
                onClick={() => {
                  setSelected(null);
                  setGiftOpen(false);
                }}
                className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition"
              >
                <CloseIcon size={14} />
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {tradeOpen && selected && (
          <TradeComposer
            key="composer"
            api={api}
            seedScene={selected}
            onClose={() => setTradeOpen(false)}
            onCreated={(result) => {
              setTradeOpen(false);
              setSelected(null);
              setGiftFlash({
                tone: "success",
                text: `交易已发出 · offer #${result.offer_id}`,
              });
              setTimeout(() => setGiftFlash(null), 3200);
            }}
          />
        )}
      </AnimatePresence>
    </MetaShell>
  );
}

/* ── AchievementsView ────────────────────────────────────────────────────── */

const KIND_LABELS = {
  pioneer: { name: "开荒者", icon: "初", color: "amber" },
  collector: { name: "收藏家", icon: "集", color: "purple" },
  hidden: { name: "隐藏", icon: "隐", color: "slate" },
};

function AchievementsView({ api }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pool, setPool] = useState({ balance_usd: 0, total_paid_out_usd: 0 });
  const [redeeming, setRedeeming] = useState(null); // achievement id in flight
  const [flash, setFlash] = useState(null);

  async function refresh() {
    try {
      const [a, p] = await Promise.all([
        api.gameMyAchievements(),
        api.gameRewardPool().catch(() => ({ data: { balance_usd: 0, total_paid_out_usd: 0 } })),
      ]);
      setEntries(a.data.entries || []);
      setPool(p.data || { balance_usd: 0, total_paid_out_usd: 0 });
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refresh();
      if (cancelled) return;
    })();
    return () => { cancelled = true; };
  }, []);

  async function handleRedeem(a) {
    if (redeeming) return;
    setRedeeming(a.id);
    try {
      const { data } = await api.gameRedeemAchievement(a.id);
      setFlash({
        tone: "success",
        text: `+$${data.reward_usd.toFixed(2)} · 账户余额 $${data.balance_after.toFixed(2)}`,
      });
      await refresh();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "object" ? detail.code : null;
      const msg = {
        pool_empty: "奖池暂时见底，稍后再来兑换。",
        already_redeemed: "该成就已兑换过。",
        not_redeemable: "该成就暂未设定奖励。",
      }[code] || "兑换失败";
      setFlash({ tone: "error", text: msg });
    } finally {
      setRedeeming(null);
      setTimeout(() => setFlash(null), 3000);
    }
  }

  const grouped = useMemo(() => {
    const map = { pioneer: [], collector: [], hidden: [] };
    for (const e of entries) {
      (map[e.kind] || map.hidden).push(e);
    }
    return map;
  }, [entries]);

  const redeemableTotal = entries
    .filter((e) => e.redeemable)
    .reduce((sum, e) => sum + Number(e.reward_usd || 0), 0);

  const headline = (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold pixel-font tracking-widest bg-slate-900 dark:bg-white text-white dark:text-slate-900">
        已解锁 · {entries.length}
      </span>
      {redeemableTotal > 0 && (
        <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border border-emerald-400/40">
          可兑换 ${redeemableTotal.toFixed(2)}
        </span>
      )}
      <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-[11px] text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
        奖池 ${Number(pool.balance_usd || 0).toFixed(2)} · 已发放 $
        {Number(pool.total_paid_out_usd || 0).toFixed(2)}
      </span>
    </div>
  );

  return (
    <MetaShell kicker="成就" title="我的荣誉" actions={headline}>
      {flash && (
        <div
          className={`rounded-xl px-4 py-2 text-sm font-semibold ${
            flash.tone === "success"
              ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border border-emerald-400/40"
              : "bg-red-500/15 text-red-600 dark:text-red-300 border border-red-400/40"
          }`}
        >
          {flash.text}
        </div>
      )}
      {loading ? (
        <MetaEmpty text="加载中…" />
      ) : entries.length === 0 ? (
        <MetaEmpty text="还没有解锁任何成就。完成冒险、收集 CG 来解锁吧。" />
      ) : (
        <div className="space-y-6">
          {Object.entries(KIND_LABELS).map(([kind, meta]) => {
            const list = grouped[kind];
            if (!list || list.length === 0) return null;
            return (
              <section key={kind}>
                <div className="flex items-baseline justify-between mb-3">
                  <h3 className="pixel-font text-[11px] tracking-[0.3em] uppercase text-slate-500 dark:text-slate-400 flex items-center gap-2.5">
                    <span className={`w-5 h-5 rounded-md ${(KIND_THEME[meta.color] || KIND_THEME.slate).iconBg} flex items-center justify-center text-[10px] font-black ${(KIND_THEME[meta.color] || KIND_THEME.slate).iconText} pixel-font`}>
                      {meta.icon}
                    </span>
                    <span>{meta.name}</span>
                  </h3>
                  <span className="pixel-font text-[10px] text-slate-400">
                    {String(list.length).padStart(2, "0")}
                  </span>
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {list.map((a) => (
                    <AchievementCard
                      key={a.id}
                      a={a}
                      meta={meta}
                      redeeming={redeeming === a.id}
                      onRedeem={() => handleRedeem(a)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </MetaShell>
  );
}

const KIND_THEME = {
  amber: {
    gradient: "from-amber-500/20 via-amber-400/5 to-transparent",
    glow: "shadow-amber-500/10",
    ring: "ring-amber-400/30",
    iconBg: "bg-amber-500/15",
    iconText: "text-amber-500 dark:text-amber-400",
    accent: "text-amber-600 dark:text-amber-400",
    dot: "bg-amber-400",
    redeemBg: "bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400",
    redeemShadow: "shadow-amber-500/25",
  },
  purple: {
    gradient: "from-purple-500/20 via-purple-400/5 to-transparent",
    glow: "shadow-purple-500/10",
    ring: "ring-purple-400/30",
    iconBg: "bg-purple-500/15",
    iconText: "text-purple-500 dark:text-purple-400",
    accent: "text-purple-600 dark:text-purple-400",
    dot: "bg-purple-400",
    redeemBg: "bg-gradient-to-r from-purple-500 to-fuchsia-500 hover:from-purple-400 hover:to-fuchsia-400",
    redeemShadow: "shadow-purple-500/25",
  },
  slate: {
    gradient: "from-slate-500/15 via-slate-400/5 to-transparent",
    glow: "shadow-slate-500/8",
    ring: "ring-slate-400/20",
    iconBg: "bg-slate-500/10",
    iconText: "text-slate-500 dark:text-slate-400",
    accent: "text-slate-600 dark:text-slate-400",
    dot: "bg-slate-400",
    redeemBg: "bg-gradient-to-r from-slate-500 to-slate-600 hover:from-slate-400 hover:to-slate-500",
    redeemShadow: "shadow-slate-500/20",
  },
};

function AchievementCard({ a, meta, redeeming, onRedeem }) {
  const reward = Number(a.reward_usd || 0);
  const redeemed = !!a.redeemed_at;
  const t = KIND_THEME[meta.color || "slate"] || KIND_THEME.slate;
  return (
    <div className={`group relative rounded-2xl overflow-hidden transition-all duration-300 hover:scale-[1.01] ${
      redeemed ? "opacity-60 grayscale-[0.3] hover:opacity-80 hover:grayscale-0" : ""
    }`}>
      {/* ambient glow — only on unredeemed */}
      {!redeemed && (
        <div className={`absolute -inset-px rounded-2xl ${t.glow} shadow-lg blur-sm opacity-60 group-hover:opacity-100 transition-opacity`} />
      )}

      {/* card body */}
      <div className={`relative rounded-2xl bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm border border-slate-200/60 dark:border-slate-700/40 ring-1 ${t.ring}`}>
        {/* gradient wash */}
        <div className={`absolute inset-0 bg-gradient-to-br ${t.gradient} rounded-2xl pointer-events-none`} />

        <div className="relative px-4 py-3.5">
          <div className="flex items-start gap-3">
            {/* icon */}
            <div className={`shrink-0 w-10 h-10 rounded-xl ${t.iconBg} flex items-center justify-center ring-1 ring-inset ring-white/10`}>
              <span className={`text-[13px] font-black ${t.iconText} pixel-font tracking-wider`}>
                {meta.icon}
              </span>
            </div>

            {/* text */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <div className="font-bold text-slate-800 dark:text-slate-100 text-[13px] leading-tight truncate">
                  {a.title}
                </div>
                {!redeemed && reward > 0 && (
                  <span className={`shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-bold ${t.accent} ${t.iconBg} pixel-font tracking-wider`}>
                    ${reward.toFixed(2)}
                  </span>
                )}
              </div>
              {a.detail && (
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed line-clamp-2">
                  {a.detail}
                </div>
              )}
            </div>

            {/* date */}
            <div className="text-[9px] text-slate-400 shrink-0 mt-0.5 pixel-font tracking-widest">
              {(a.awarded_at || "").slice(5, 10)}
            </div>
          </div>

          {/* redeem row */}
          {reward > 0 && (
            <div className="mt-3 flex items-center justify-end">
              {redeemed ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 dark:bg-slate-800/60 text-slate-400 line-through pixel-font tracking-wider">
                  已兑换 ${reward.toFixed(2)}
                </span>
              ) : (
                <button
                  type="button"
                  disabled={redeeming}
                  onClick={onRedeem}
                  className={`relative inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-[11px] font-bold text-white ${t.redeemBg} shadow-md ${t.redeemShadow} transition-all duration-200 hover:shadow-lg hover:scale-[1.03] active:scale-[0.98] disabled:opacity-60 disabled:cursor-wait disabled:hover:scale-100`}
                >
                  {redeeming ? (
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      兑换中
                    </span>
                  ) : (
                    `兑换 $${reward.toFixed(2)}`
                  )}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── TradesView ─────────────────────────────────────────────────────────── */

const TRADE_SUB_TABS = [
  { key: "incoming", label: "收到的" },
  { key: "outgoing", label: "发出的" },
  { key: "history", label: "历史" },
];

const TRADE_STATUS_META = {
  pending: { label: "等待中", tone: "amber" },
  accepted: { label: "已成交", tone: "emerald" },
  rejected: { label: "已拒绝", tone: "red" },
  cancelled: { label: "已撤回", tone: "slate" },
  expired: { label: "已过期", tone: "slate" },
};

function TradesView({ api }) {
  const [sub, setSub] = useState("incoming");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null); // offer object for detail modal
  const [acting, setActing] = useState(null); // action in flight
  const [flash, setFlash] = useState(null);

  async function refresh() {
    setLoading(true);
    try {
      const fn = sub === "incoming" ? api.gameTradesIncoming
        : sub === "outgoing" ? api.gameTradesOutgoing
        : api.gameTradesHistory;
      const { data } = await fn();
      setItems(data.items || []);
    } catch { /* */ } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, [sub]);

  async function openDetail(id) {
    try {
      const { data } = await api.gameGetTrade(id);
      setDetail({ ...(data.offer || {}), _scope: sub });
    } catch { /* */ }
  }

  async function act(action, id) {
    setActing(action);
    try {
      const fn = action === "accept" ? api.gameAcceptTrade
        : action === "reject" ? api.gameRejectTrade
        : api.gameCancelTrade;
      await fn(id);
      setDetail(null);
      setFlash({ tone: "success", text: action === "accept" ? "交易已成交" : action === "reject" ? "已拒绝" : "已撤回" });
      setTimeout(() => setFlash(null), 3000);
      refresh();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "object" ? detail.code : null;
      setFlash({ tone: "error", text: {
        wrong_role: "无权执行此操作",
        already_responded: "该交易已处理",
        expired: "该交易已过期",
        not_owned_anymore: "CG 已不在手中",
        already_owned: "对方已拥有此 CG",
      }[code] || "操作失败" });
      setTimeout(() => setFlash(null), 3000);
    } finally {
      setActing(null);
    }
  }

  return (
    <MetaShell kicker="交易" title="交易中心">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
        <div className="grid grid-cols-3 gap-2">
          <CollectionStat label="当前" value={items.length} icon={<ArrowLeftRight size={12} />} />
          <CollectionStat label="出价" value={items.reduce((n, it) => n + (it.offered_scenes?.length || 0), 0)} icon={<Send size={12} />} />
          <CollectionStat label="求购" value={items.reduce((n, it) => n + (it.wanted_scenes?.length || 0), 0)} icon={<Gift size={12} />} />
        </div>
        <SegmentTabs items={TRADE_SUB_TABS} value={sub} onChange={setSub} />
      </div>

      <FlashNotice flash={flash} />

      {loading ? (
        <MetaEmpty text="加载中…" />
      ) : items.length === 0 ? (
        <MetaEmpty text={sub === "incoming" ? "暂无收到的交易" : sub === "outgoing" ? "暂无发出的交易" : "暂无交易历史"} />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {items.map((o) => {
            const sm = TRADE_STATUS_META[o.status] || TRADE_STATUS_META.pending;
            const isIncoming = sub === "incoming";
            const peer = isIncoming ? o.from_display_name : o.to_display_name;
            return (
              <button
                key={o.id}
                type="button"
                onClick={() => openDetail(o.id)}
                className="w-full text-left"
              >
                <MetaCard>
                  <div className="p-4 space-y-4">
                    {/* header row */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-black text-slate-800 dark:text-slate-100">
                          {isIncoming ? `来自 ${peer || "匿名"}` : `发给 ${peer || "匿名"}`}
                        </span>
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold pixel-font tracking-widest ${
                          sm.tone === "amber" ? "bg-amber-500/15 text-amber-600 dark:text-amber-300" :
                          sm.tone === "emerald" ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300" :
                          sm.tone === "red" ? "bg-red-500/15 text-red-600 dark:text-red-300" :
                          "bg-slate-100 dark:bg-slate-800 text-slate-500"
                        }`}>
                          {sm.label}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-400 pixel-font tracking-widest">
                        #{o.id}
                      </span>
                    </div>

                    {/* scene previews */}
                    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                      <div>
                        <div className="mb-1 text-[10px] text-slate-400 pixel-font tracking-widest">出价</div>
                        <CgThumbStack items={o.offered_preview || []} />
                      </div>
                      <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-1 text-slate-400 text-xs">⇄</span>
                      <div className="text-right">
                        <div className="mb-1 text-[10px] text-slate-400 pixel-font tracking-widest">求购</div>
                        <div className="flex justify-end">
                          <CgThumbStack items={o.wanted_preview || []} />
                        </div>
                      </div>
                    </div>

                    {o.message && (
                      <div className="text-xs text-slate-500 dark:text-slate-400 italic line-clamp-1">
                        "{o.message}"
                      </div>
                    )}
                  </div>
                </MetaCard>
              </button>
            );
          })}
        </div>
      )}

      {/* detail modal */}
      <AnimatePresence>
        {detail && (
          <motion.div
            key="trade-detail"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[115] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
            onClick={() => setDetail(null)}
          >
            <motion.div
              initial={{ scale: 0.92, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.92, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="relative w-full max-w-4xl max-h-[86vh] rounded-3xl bg-slate-950 border border-white/10 shadow-2xl overflow-y-auto text-slate-100"
            >
              {/* close */}
              <button
                onClick={() => setDetail(null)}
                className="absolute top-3 right-3 w-7 h-7 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition z-10"
              >
                <CloseIcon size={13} />
              </button>

              <div className="p-5 md:p-6 space-y-5">
                {/* header */}
                <div className="flex items-start justify-between gap-4 pr-8">
                  <div>
                    <div className="pixel-font text-[10px] tracking-[0.3em] uppercase text-emerald-300">
                      交易 #{detail.id}
                    </div>
                    <div className="mt-1 text-2xl font-black tracking-tight">
                      {detail.from_display_name || `用户 #${detail.from_user_id}`} ⇄ {detail.to_display_name || `用户 #${detail.to_user_id}`}
                    </div>
                  </div>
                  {(() => {
                    const sm = TRADE_STATUS_META[detail.status] || TRADE_STATUS_META.pending;
                    return (
                      <span className={`px-3 py-1 rounded-full text-[10px] font-bold pixel-font ${
                        sm.tone === "amber" ? "bg-amber-500/20 text-amber-300" :
                        sm.tone === "emerald" ? "bg-emerald-500/20 text-emerald-300" :
                        sm.tone === "red" ? "bg-red-500/20 text-red-300" :
                        "bg-slate-800 text-slate-400"
                      }`}>
                        {sm.label}
                      </span>
                    );
                  })()}
                </div>

                {/* parties */}
                <div className="grid grid-cols-[1fr_auto_1fr] items-stretch gap-3 text-sm">
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-500 uppercase pixel-font tracking-widest">
                      <UserRound size={12} /> 发送方
                    </div>
                    <div className="mt-1 font-bold text-slate-100">{detail.from_display_name || `用户 #${detail.from_user_id}`}</div>
                  </div>
                  <div className="flex items-center text-emerald-400 text-xl">⇄</div>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-right">
                    <div className="flex items-center justify-end gap-1.5 text-[10px] text-slate-500 uppercase pixel-font tracking-widest">
                      接收方 <UserRound size={12} />
                    </div>
                    <div className="mt-1 font-bold text-slate-100">{detail.to_display_name || `用户 #${detail.to_user_id}`}</div>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr]">
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="text-xs font-bold text-slate-300 mb-2">
                      出价 CG <span className="text-slate-500">({(detail.offered_preview || []).length})</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {(detail.offered_preview || []).map((s) => (
                        <div key={s.id} className="relative aspect-[4/3] rounded-xl overflow-hidden border border-white/10">
                          <img src={s.image_url} alt="" className="w-full h-full object-cover pixel-canvas" />
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="hidden md:flex items-center text-2xl text-emerald-400">⇄</div>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="text-xs font-bold text-slate-300 mb-2">
                      求购 CG <span className="text-slate-500">({(detail.wanted_preview || []).length})</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {(detail.wanted_preview || []).map((s) => (
                        <div key={s.id} className="relative aspect-[4/3] rounded-xl overflow-hidden border border-white/10">
                          <img src={s.image_url} alt="" className="w-full h-full object-cover pixel-canvas" />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {detail.message && (
                  <div className="rounded-xl bg-slate-900 border border-slate-800 px-4 py-3 text-sm text-slate-300 italic">
                    "{detail.message}"
                  </div>
                )}

                {/* actions — only for pending offers */}
                {detail.status === "pending" && (() => {
                  const isIncoming = detail._scope === "incoming";
                  const isOutgoing = detail._scope === "outgoing";
                  return (
                    <div className="flex gap-2 pt-2 border-t border-white/10">
                      {isIncoming && (
                        <>
                          <button
                            type="button"
                            onClick={() => act("accept", detail.id)}
                            disabled={!!acting}
                            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl text-sm font-bold bg-emerald-500 hover:bg-emerald-400 text-white disabled:opacity-50 transition"
                          >
                            <CheckCircle2 size={15} /> {acting === "accept" ? "处理中…" : "接受交易"}
                          </button>
                          <button
                            type="button"
                            onClick={() => act("reject", detail.id)}
                            disabled={!!acting}
                            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl text-sm font-bold bg-red-500/80 hover:bg-red-400 text-white disabled:opacity-50 transition"
                          >
                            <XCircle size={15} /> {acting === "reject" ? "处理中…" : "拒绝"}
                          </button>
                        </>
                      )}
                      {isOutgoing && (
                        <button
                          type="button"
                          onClick={() => act("cancel", detail.id)}
                          disabled={!!acting}
                          className="flex-1 px-3 py-2.5 rounded-xl text-sm font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-50 transition"
                        >
                          {acting === "cancel" ? "撤回中…" : "撤回交易"}
                        </button>
                      )}
                    </div>
                  );
                })()}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </MetaShell>
  );
}

/* ── MarketView ─────────────────────────────────────────────────────────── */

const MARKET_TABS = [
  { key: "all", label: "全服" },
  { key: "my", label: "我的挂单" },
  { key: "bought", label: "买到的" },
];

function MarketView({ api }) {
  const [tab, setTab] = useState("all");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [flash, setFlash] = useState(null);
  const [buying, setBuying] = useState(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("new");
  const [confirmItem, setConfirmItem] = useState(null);

  async function refresh() {
    setLoading(true);
    try {
      const { data } = await api.gameListMarket(tab);
      setItems(data.items || []);
    } catch { /* */ } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, [tab]);

  async function buy(id) {
    setBuying(id);
    try {
      await api.gameBuyListing(id);
      setFlash({ tone: "success", text: "购买成功" });
      setTimeout(() => setFlash(null), 3000);
      refresh();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "object" ? detail.code : null;
      setFlash({ tone: "error", text: {
        insufficient_balance: "余额不足",
        already_sold: "已被买走",
        self_buy: "不能购买自己的挂单",
      }[code] || "购买失败" });
      setTimeout(() => setFlash(null), 3000);
    } finally {
      setBuying(null);
    }
  }

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = items.filter((it) => {
      if (!q) return true;
      return [
        it.seller_name,
        genreName(it.genre),
        cgCode(it.scene_id),
        it.message,
      ].join(" ").toLowerCase().includes(q);
    });
    return [...list].sort((a, b) => {
      if (sort === "price_asc") return Number(a.price_usd || 0) - Number(b.price_usd || 0);
      if (sort === "price_desc") return Number(b.price_usd || 0) - Number(a.price_usd || 0);
      if (sort === "keynote") return Number(b.is_keynote || 0) - Number(a.is_keynote || 0);
      return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    });
  }, [items, query, sort]);

  const minPrice = items.length ? Math.min(...items.map((it) => Number(it.price_usd || 0)).filter((n) => n > 0)) : 0;
  const avgPrice = items.length
    ? items.reduce((sum, it) => sum + Number(it.price_usd || 0), 0) / items.length
    : 0;

  async function cancel(id) {
    try {
      await api.gameCancelListing(id);
      setFlash({ tone: "success", text: "已撤回" });
      setTimeout(() => setFlash(null), 3000);
      refresh();
    } catch {
      setFlash({ tone: "error", text: "撤回失败" });
      setTimeout(() => setFlash(null), 3000);
    }
  }

  return (
    <MetaShell kicker="市场" title="CG 交易所">
      <div className="grid gap-3 md:grid-cols-3">
        <CollectionStat label="在列" value={items.length} icon={<Store size={12} />} />
        <CollectionStat label="最低价" value={minPrice ? `$${minPrice.toFixed(2)}` : "-"} icon={<ShoppingBag size={12} />} />
        <CollectionStat label="均价" value={avgPrice ? `$${avgPrice.toFixed(2)}` : "-"} icon={<Tag size={12} />} />
      </div>

      <MetaCard className="p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <SegmentTabs items={MARKET_TABS} value={tab} onChange={setTab} />
          <div className="flex items-center gap-2">
            <div className="relative min-w-[13rem]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索卖家、题材、编号"
                className="w-full rounded-full border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-950/70 pl-9 pr-3 py-2 text-xs text-slate-700 dark:text-slate-200 outline-none focus:border-emerald-400"
              />
            </div>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="rounded-full border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-950/70 px-3 py-2 text-xs text-slate-700 dark:text-slate-200 outline-none focus:border-emerald-400"
            >
              <option value="new">最新上架</option>
              <option value="price_asc">价格从低到高</option>
              <option value="price_desc">价格从高到低</option>
              <option value="keynote">关键场景优先</option>
            </select>
          </div>
        </div>
      </MetaCard>

      <FlashNotice flash={flash} />

      {loading ? (
        <MetaEmpty text="加载中…" />
      ) : items.length === 0 ? (
        <MetaEmpty text={tab === "my" ? "你还没有挂单" : tab === "bought" ? "还没有买到的" : "市场暂无在售"} />
      ) : visibleItems.length === 0 ? (
        <MetaEmpty text="没有符合筛选条件的挂单。" />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3">
          {visibleItems.map((it) => (
            <div key={it.id} className="group rounded-2xl overflow-hidden bg-white/80 dark:bg-slate-950/70 border border-slate-200/80 dark:border-white/10 shadow-sm transition hover:-translate-y-0.5 hover:shadow-xl">
              <div className="relative aspect-[4/3] bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <img
                  src={it.image_url}
                  alt=""
                  loading="lazy"
                  className="w-full h-full object-cover pixel-canvas transition duration-500 group-hover:scale-[1.04]"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-transparent to-transparent pointer-events-none" />
                <div className="absolute inset-0 pixel-scanlines opacity-15 pointer-events-none" />
                <div className="absolute top-2 right-2 px-2.5 py-1 rounded-xl bg-black/75 text-emerald-300 text-xs font-bold pixel-font tracking-wider shadow">
                  ${Number(it.price_usd).toFixed(2)}
                </div>
                {it.is_keynote ? (
                  <div className="absolute top-2 left-2 px-2 py-1 rounded-xl bg-amber-500/90 text-white text-[10px] font-black pixel-font tracking-widest">
                    KEY
                  </div>
                ) : null}
              </div>
              <div className="p-3 space-y-2">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-300 pixel-font tracking-widest">
                    {it.seller_name || "匿名"}
                  </span>
                  {it.genre && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-500 dark:text-indigo-300 pixel-font tracking-widest">
                      {genreName(it.genre)}
                    </span>
                  )}
                </div>
                {it.message && (
                  <div className="text-[11px] text-slate-400 italic line-clamp-1">"{it.message}"</div>
                )}
                {tab === "my" ? (
                  <button
                    type="button"
                    onClick={() => cancel(it.id)}
                    className="w-full px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700 transition"
                  >
                    撤回挂单
                  </button>
                ) : tab === "all" ? (
                  <button
                    type="button"
                    onClick={() => setConfirmItem(it)}
                    disabled={buying === it.id}
                    className="w-full px-3 py-1.5 rounded-lg text-xs font-bold bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white shadow transition disabled:opacity-60"
                  >
                    {buying === it.id ? "购买中…" : `查看并购买`}
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
      <AnimatePresence>
        {confirmItem && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[115] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
            onClick={() => setConfirmItem(null)}
          >
            <motion.div
              initial={{ scale: 0.94, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.94, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md overflow-hidden rounded-3xl bg-slate-950 border border-white/10 text-slate-100 shadow-2xl"
            >
              <img src={confirmItem.image_url} alt="" className="w-full aspect-[4/3] object-cover pixel-canvas" />
              <div className="p-5 space-y-4">
                <div>
                  <div className="pixel-font text-[10px] tracking-[0.3em] uppercase text-emerald-300">
                    购买确认
                  </div>
                  <div className="mt-1 text-3xl font-black">${Number(confirmItem.price_usd).toFixed(2)}</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4">
                  <DetailRow label="编号" value={cgCode(confirmItem.scene_id)} />
                  <DetailRow label="题材" value={genreName(confirmItem.genre)} />
                  <DetailRow label="卖家" value={confirmItem.seller_name || "匿名"} />
                  <DetailRow label="回合" value={`第 ${confirmItem.turn_idx} 回`} />
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setConfirmItem(null)}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-slate-200 text-sm font-bold transition"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      const id = confirmItem.id;
                      setConfirmItem(null);
                      await buy(id);
                    }}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-bold transition"
                  >
                    确认购买
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </MetaShell>
  );
}

/* ── AwardStack ── floating achievement unlocks (up to 3 at a time) ──────── */

const MAX_TOAST_STACK = 3;

function AwardStack({ awards }) {
  const visible = awards.slice(0, MAX_TOAST_STACK);
  const overflow = Math.max(0, awards.length - visible.length);
  return (
    <div className="fixed bottom-6 right-6 z-[120] flex flex-col-reverse gap-2 pointer-events-none">
      <AnimatePresence initial={false}>
        {visible.map((award, idx) => (
          <AwardCard
            key={`${award.slug}-${idx}`}
            award={award}
            // Stacking index: the latest (idx 0 from the head of the queue)
            // sits at the bottom and is fully opaque; older cards climb up
            // with slight fade so the eye reads them as a pile.
            depth={idx}
          />
        ))}
      </AnimatePresence>
      {overflow > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 0.8, y: 0 }}
          className="pointer-events-none self-end px-2.5 py-1 rounded-full bg-slate-900/80 border border-slate-600/60 text-[10px] font-semibold text-slate-300 pixel-font tracking-widest"
        >
          +{overflow} 条待播
        </motion.div>
      )}
    </div>
  );
}

function AwardCard({ award, depth }) {
  const meta = KIND_LABELS[award.kind] || KIND_LABELS.hidden;
  const t = KIND_THEME[meta.color || "slate"] || KIND_THEME.slate;
  return (
    <motion.div
      initial={{ opacity: 0, x: 80 }}
      animate={{
        opacity: 1 - depth * 0.15,
        x: 0,
        scale: 1 - depth * 0.03,
      }}
      exit={{ opacity: 0, x: 80 }}
      transition={{ type: "spring", stiffness: 420, damping: 28 }}
      className="pointer-events-auto max-w-xs"
    >
      {/* glow */}
      <div className={`absolute -inset-1 rounded-2xl ${t.glow} shadow-lg blur-sm opacity-50`} />
      <div className={`relative rounded-2xl bg-white/90 dark:bg-slate-900/90 backdrop-blur-md shadow-2xl border border-slate-200/60 dark:border-slate-700/40 ring-1 ${t.ring} overflow-hidden`}>
        {/* gradient wash */}
        <div className={`absolute inset-0 bg-gradient-to-br ${t.gradient} pointer-events-none`} />
        <div className="relative p-3.5 flex items-start gap-3">
          <div className={`shrink-0 w-9 h-9 rounded-xl ${t.iconBg} flex items-center justify-center ring-1 ring-inset ring-white/10`}>
            <span className={`text-xs font-black ${t.iconText} pixel-font`}>{meta.icon}</span>
          </div>
          <div className="min-w-0">
            <div className="text-[10px] font-bold uppercase tracking-widest text-amber-600 dark:text-amber-400">
              成就解锁
            </div>
            <div className="font-bold text-slate-800 dark:text-slate-100 text-sm mt-0.5 truncate">
              {award.title}
            </div>
            {award.detail && (
              <div className="text-[11px] text-slate-500 mt-0.5 line-clamp-2">
                {award.detail}
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
