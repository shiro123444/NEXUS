import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  Key,  LayoutDashboard,  LogOut,  Settings,  History as HistoryIcon,  Plus,
  Trash2,  Copy,  Activity,  AlertCircle,  Moon,  Sun, Trophy, Target,
  Menu,  X,  CreditCard,  Zap,  CheckCircle2, Calendar, ChevronLeft, ChevronRight, ChevronDown, Image as ImageIcon,
  Mail, Lock, ShieldCheck, User, Camera, Gamepad2
} from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from "recharts";
import logoImg from "../assets/logo.png";
import GameModule from "./game/GameModule";
import "./game/pixelStyles.css";

const api = {
  getBg: () => axios.get("/api/bg/active"),
  checkAuth: () => axios.get("/api/auth/me"),
  login: (data) => axios.post("/api/auth/login", data),
  register: (data) => axios.post("/api/auth/register", data),
  getRegisterConfig: () => axios.get("/api/auth/register-config"),
  sendEmailCode: (email) => axios.post("/api/auth/send-email-code", { email }),
  sendResetPasswordEmailCode: (data) => axios.post("/api/auth/reset-password/send-email-code", data),
  resetPassword: (data) => axios.post("/api/auth/reset-password", data),
  sendAccountEmailCode: (email) => axios.post("/api/account/send-email-code", { email }),
  bindEmail: (data) => axios.post("/api/account/bind-email", data),
  sendChangePasswordEmailCode: () => axios.post("/api/account/change-password/send-email-code", {}),
  changePassword: (data) => axios.post("/api/account/change-password", data),
  logout: () => axios.post("/api/auth/logout"),
  getDashboard: () => axios.get("/api/dashboard"),
  getModelMarketplace: () => axios.get("/api/model-marketplace"),
  getModels: () => axios.get("/v1/models"),
  getKeys: () => axios.get("/api/keys"),
  createKey: (name = "Nexus Key") => axios.post("/api/keys", { name }),
  deleteKey: (id) => axios.delete(`/api/keys/${id}`),
  getLogs: () => axios.get("/api/logs?limit=100"),
  checkinStatus: () => axios.get('/api/user/checkin/status'),
  doCheckin: () => axios.post('/api/user/checkin', {}),
  getCheckinHistory: () => axios.get('/api/user/checkin/history'),
  getCheckinLeaderboard: () => axios.get('/api/user/checkin/leaderboard'),
  createKeyEx: (data) => axios.post("/api/keys", data),
  updateProfile: (data) => axios.put("/api/account/profile", data),
  uploadAvatar: (formData) => axios.post("/api/account/avatar", formData),

  // Game module
  gameGenres: () => axios.get("/api/game/genres"),
  gameLeaderboard: (scope = "all", sort = "score") =>
    axios.get(`/api/game/leaderboard?scope=${scope}&sort=${sort}`),
  gameHistory: () => axios.get("/api/game/history"),
  gameActiveRun: () => axios.get("/api/game/runs/active"),
  gameRunDetail: (id) => axios.get(`/api/game/runs/${id}`),
  gameRunScenes: (id, from = 0) => axios.get(`/api/game/runs/${id}/scenes?from_turn=${from}`),
  gameStartRun: (body = {}, opts = {}) =>
    axios.post("/api/game/runs", body, { signal: opts.signal }),
  gameAbandon: (id) => axios.post(`/api/game/runs/${id}/abandon`, {}),
  gameMyGallery: (genre) =>
    axios.get(`/api/game/gallery/me${genre ? `?genre=${encodeURIComponent(genre)}` : ""}`),
  gamePublicGallery: (userId, genre) =>
    axios.get(
      `/api/game/gallery/${encodeURIComponent(userId)}${
        genre ? `?genre=${encodeURIComponent(genre)}` : ""
      }`
    ),
  gameMyAchievements: () => axios.get("/api/game/achievements/me"),
  gameRedeemAchievement: (id) =>
    axios.post(`/api/game/achievements/${encodeURIComponent(id)}/redeem`, {}),
  gameRewardPool: () => axios.get("/api/game/reward-pool"),
  gameLookupUser: (studentId) =>
    axios.get(`/api/game/users/lookup?student_id=${encodeURIComponent(studentId)}`),
  gameLookupByName: (name) =>
    axios.get(`/api/game/users/lookup?name=${encodeURIComponent(name)}`),
  gameSendGift: (body) => axios.post("/api/game/gifts", body),
  gameGiftsSent: () => axios.get("/api/game/gifts/sent"),
  gameGiftsReceived: () => axios.get("/api/game/gifts/received"),
  gameCreateTrade: (body) => axios.post("/api/game/trades", body),
  gameTradesIncoming: () => axios.get("/api/game/trades/incoming"),
  gameTradesOutgoing: () => axios.get("/api/game/trades/outgoing"),
  gameTradesHistory: () => axios.get("/api/game/trades/history"),
  gameGetTrade: (id) => axios.get(`/api/game/trades/${encodeURIComponent(id)}`),
  gameAcceptTrade: (id) =>
    axios.post(`/api/game/trades/${encodeURIComponent(id)}/accept`, {}),
  gameRejectTrade: (id) =>
    axios.post(`/api/game/trades/${encodeURIComponent(id)}/reject`, {}),
  gameCancelTrade: (id) =>
    axios.post(`/api/game/trades/${encodeURIComponent(id)}/cancel`, {}),
  // Marketplace
  gameCreateListing: (body) => axios.post("/api/game/marketplace", body),
  gameListMarket: (scope = "all", limit = 50) =>
    axios.get(`/api/game/marketplace?scope=${scope}&limit=${limit}`),
  gameBuyListing: (id) =>
    axios.post(`/api/game/marketplace/${encodeURIComponent(id)}/buy`, {}),
  gameCancelListing: (id) =>
    axios.post(`/api/game/marketplace/${encodeURIComponent(id)}/cancel`, {}),
  // Admin rewards
  gameAdminRewards: () => axios.get("/api/game/admin/rewards"),
  gameAdminSetReward: (slug, reward_usd) =>
    axios.post("/api/game/admin/rewards", { slug, reward_usd }),
  // Streaming variant: POSTs the same body but reads a text/event-stream response.
  // `handlers` may define onStart, onDelta, onMeta, onDone, onError.
  // Returns an AbortController the caller can use to cancel on unmount.
  gameActStream: (id, action, choiceIndex, handlers = {}) => {
    const controller = new AbortController();
    (async () => {
      const { onStart, onDelta, onMeta, onDone, onError } = handlers;
      let resp;
      try {
        resp = await fetch(`/api/game/runs/${id}/act`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ action, choice_index: choiceIndex }),
          signal: controller.signal,
        });
      } catch (err) {
        if (err?.name !== "AbortError") onError?.({ detail: String(err?.message || err) });
        return;
      }
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
          const j = await resp.json();
          detail = j?.detail || detail;
        } catch (_) { /* body not JSON */ }
        onError?.({ detail });
        return;
      }
      if (!resp.body) {
        onError?.({ detail: "streaming not supported by browser" });
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8", { fatal: false });
      let buffer = "";
      const dispatch = (event, data) => {
        let parsed = {};
        if (data) {
          try { parsed = JSON.parse(data); } catch (_) { return; }
        }
        if (event === "start") onStart?.(parsed);
        else if (event === "delta") onDelta?.(parsed);
        else if (event === "meta") onMeta?.(parsed);
        else if (event === "done") onDone?.(parsed);
        else if (event === "error") onError?.(parsed);
      };
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            let event = "message";
            const dataLines = [];
            for (const line of frame.split("\n")) {
              if (line.startsWith("event:")) event = line.slice(6).trim();
              else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
            }
            dispatch(event, dataLines.join("\n"));
          }
        }
        buffer += decoder.decode();
      } catch (err) {
        if (err?.name !== "AbortError") onError?.({ detail: String(err?.message || err) });
      }
    })();
    return controller;
  },
};

const MARKETPLACE_MODEL_META = {
  "claude-haiku-4.5": {
    family: "haiku",
    context_window: 200000,
    max_output_tokens: 64000,
    description: "轻量低延迟，适合日常问答与工具编排。",
    display_name: "Claude Haiku 4.5",
  },
  "claude-sonnet-4.5": {
    family: "sonnet",
    context_window: 200000,
    max_output_tokens: 64000,
    description: "均衡性能与成本，适合大多数开发任务。",
    display_name: "Claude Sonnet 4.5",
  },
  "claude-sonnet-4.6": {
    family: "sonnet",
    context_window: 1000000,
    max_output_tokens: 64000,
    description: "长上下文场景优先，适合大仓库和长链路任务。",
    display_name: "Claude Sonnet 4.6",
  },
  "claude-opus-4.6": {
    family: "opus",
    context_window: 1000000,
    max_output_tokens: 64000,
    description: "旗舰推理模型，适合复杂分析、数学和深度代码任务。",
    display_name: "Claude Opus 4.6",
  },
  "claude-opus-4.7": {
    family: "opus",
    context_window: 1000000,
    max_output_tokens: 64000,
    description: "最新旗舰推理模型，顶尖复杂任务处理能力。",
    display_name: "Claude Opus 4.7",
  },
  "kimi-k2.6": {
    family: "kimi",
    context_window: 128000,
    max_output_tokens: 32000,
    description: "擅长长上下文理解、中文表达与通用推理，适合问答、总结、写作和代码辅助。",
    display_name: "Kimi K2.6",
  },
  "mimo-v2.5-pro": {
    family: "mimo",
    context_window: 1048576,
    max_output_tokens: 131072,
    description: "MIMO 高配主力模型，适合复杂推理、长上下文分析与稳定代码任务。",
    display_name: "MIMO V2.5 Pro",
  },
  "mimo-v2.5": {
    family: "mimo",
    context_window: 1048576,
    max_output_tokens: 131072,
    description: "MIMO 通用主力模型，兼顾质量、速度与长上下文能力。",
    display_name: "MIMO V2.5",
  },
  "mimo-v2-pro": {
    family: "mimo",
    context_window: 1048576,
    max_output_tokens: 131072,
    description: "上一代高性能 MIMO 模型，适合推理、总结和通用开发问答。",
    display_name: "MIMO V2 Pro",
  },
  "mimo-v2-flash": {
    family: "mimo",
    context_window: 256000,
    max_output_tokens: 131072,
    description: "低延迟版本，适合高频调用、轻量生成和快速响应场景。",
    display_name: "MIMO V2 Flash",
  },
  "mimo-v2-omni": {
    family: "mimo",
    context_window: 256000,
    max_output_tokens: 131072,
    description: "多模态版本，适合文本与语音等综合交互场景。",
    display_name: "MIMO V2 Omni",
  },
  "mimo-v2.5-tts": {
    family: "mimo",
    context_window: 8192,
    max_output_tokens: 8192,
    description: "MIMO 标准语音合成模型。",
    display_name: "MIMO V2.5 TTS",
  },
  "mimo-v2.5-tts-voicedesign": {
    family: "mimo",
    context_window: 8192,
    max_output_tokens: 8192,
    description: "支持声线设计的语音合成模型。",
    display_name: "MIMO V2.5 TTS VoiceDesign",
  },
  "mimo-v2.5-tts-voiceclone": {
    family: "mimo",
    context_window: 8192,
    max_output_tokens: 8192,
    description: "支持音色克隆的语音合成模型。",
    display_name: "MIMO V2.5 TTS VoiceClone",
  },
  "mimo-v2-tts": {
    family: "mimo",
    context_window: 8192,
    max_output_tokens: 8192,
    description: "轻量语音合成版本，适合基础语音输出需求。",
    display_name: "MIMO V2 TTS",
  },
  "gpt-5.2": {
    family: "gpt",
    context_window: 200000,
    max_output_tokens: 128000,
    description: "稳定通用型 GPT，适合日常问答、写作和通用开发任务。",
    display_name: "GPT-5.2",
  },
  "gpt-5.4": {
    family: "gpt",
    context_window: 200000,
    max_output_tokens: 128000,
    description: "更强推理与代码能力，适合复杂任务和长链路执行。",
    display_name: "GPT-5.4",
  },
  "gpt-5.4-mini": {
    family: "gpt",
    context_window: 200000,
    max_output_tokens: 128000,
    description: "低成本低延迟版本，适合高频轻量请求。",
    display_name: "GPT-5.4 Mini",
  },
};

const MARKETPLACE_PRICING = {
  unit: "usd_per_1m_tokens",
  notes: [],
};

function normalizeMarketplaceModelId(modelId) {
  let id = String(modelId || "").trim().toLowerCase();
  if (id === "kimi-k2.6") return id;
  if (id.startsWith("mimo-")) return id;
  if (id.startsWith("gpt-5.2") || id.startsWith("gpt-5.4")) return id;
  if (!id.startsWith("claude-")) return null;

  id = id.replace(/-(thinking|agentic)$/u, "");
  id = id.replace(/^claude-(haiku|sonnet|opus)-(\d)-(\d)(?:-\d{8})?$/u, (_, family, major, minor) => `claude-${family}-${major}.${minor}`);
  id = id.replace(/^claude-(haiku|sonnet|opus)-(\d)\.(\d)(?:-\d{8})?$/u, (_, family, major, minor) => `claude-${family}-${major}.${minor}`);
  return id;
}

function buildMarketplacePayloadFromModels(data) {
  const grouped = new Map();

  (data || []).forEach((item) => {
    const rawId = String(item?.id || "").trim();
    const normalizedId = normalizeMarketplaceModelId(rawId);

    if (!normalizedId) {
      return;
    }

    const meta = MARKETPLACE_MODEL_META[normalizedId] || {};
    const family = meta.family || normalizedId.split("-")[1] || "claude";
    const current = grouped.get(normalizedId) || {
      id: normalizedId,
      family,
      context_window: meta.context_window || 200000,
      max_output_tokens: item?.max_tokens || meta.max_output_tokens || 64000,
      description: meta.description || "",
      display_name: meta.display_name || item?.display_name || normalizedId,
      pricing_usd: meta.pricing_usd || {},
      pricing_native: meta.pricing_native || { currency: "USD" },
      variants: [],
    };

    current.max_output_tokens = item?.max_tokens || current.max_output_tokens;
    current.display_name = current.display_name || item?.display_name || normalizedId;
    if (rawId && !current.variants.includes(rawId)) {
      current.variants.push(rawId);
    }

    grouped.set(normalizedId, current);
  });

  const models = Array.from(grouped.values()).sort((a, b) => a.id.localeCompare(b.id));
  return {
    object: "model_marketplace",
    models,
    pricing: MARKETPLACE_PRICING,
  };
}

async function loadMarketplacePayload() {
  try {
    const res = await api.getModelMarketplace();
    const payload = res.data || {};
    if ((payload.models || []).length > 0) {
      return {
        ...payload,
        pricing: payload.pricing || MARKETPLACE_PRICING,
      };
    }
  } catch (error) {
    console.error(error);
  }

  try {
    const res = await api.getModels();
    return buildMarketplacePayloadFromModels(res.data?.data || []);
  } catch (error) {
    console.error(error);
    return {
      object: "model_marketplace",
      models: [],
      pricing: MARKETPLACE_PRICING,
    };
  }
}

const useDarkMode = () => {
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem("theme");
    return saved ? saved === "dark" : true;
  });

  useEffect(() => {
    const root = window.document.documentElement;
    if (isDark) {
      root.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      root.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  }, [isDark]);

  return [isDark, setIsDark];
};

function formatUsd(value) {
  const amount = Number(value || 0);
  return `$${amount.toFixed(amount >= 1 ? 4 : 6)}`;
}

function formatBalanceChartTick(timestamp, previousTimestamp) {
  const current = new Date(timestamp);
  if (Number.isNaN(current.getTime())) return "";

  const prev = previousTimestamp ? new Date(previousTimestamp) : null;
  const datePart = current.toLocaleDateString([], { month: "short", day: "numeric" });
  const timePart = current.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  if (prev && !Number.isNaN(prev.getTime()) && prev.toDateString() === current.toDateString()) {
    return timePart;
  }

  return `${datePart} ${timePart}`;
}

function formatBalanceChartTooltipLabel(timestamp) {
  const value = new Date(timestamp);
  if (Number.isNaN(value.getTime())) return String(timestamp || "");
  return value.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function keyGroupLabel(groupName) {
  if (groupName === "kimi") return "Kimi 组";
  if (groupName === "mimo") return "MIMO 组";
  if (groupName === "gpt") return "GPT 组";
  return "Claude 组";
}

function formatPricePer1M(value) {
  const amount = Number(value || 0);
  return `$${amount.toFixed(amount >= 10 ? 2 : 4)} / 1M`;
}

export default function Client() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isDark, setIsDark] = useDarkMode();
  const [bgInfo, setBgInfo] = useState({ url: '', opacity: 0 });

  useEffect(() => {
    api.getBg().then(res => {
      setBgInfo({ url: res.data.url, opacity: res.data.opacity });
    }).catch(console.error);
  }, []);

  const bgStyle = bgInfo.url ? {
    backgroundImage: `url(${bgInfo.url})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundAttachment: 'fixed'
  } : {};

  useEffect(() => {
    api.checkAuth()
      .then(res => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const handleLoginSuccess = (userData) => setUser(userData);
  const handleLogout = async () => {
    try { await api.logout(); } catch(e) {}
    setUser(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md text-slate-800 dark:text-slate-200">
        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
          <Activity size={32} className="text-slate-500" />
        </motion.div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen transition-colors duration-300 font-sans relative ${isDark ? 'dark bg-slate-950 text-slate-50' : 'bg-slate-50 text-slate-900'}`} style={bgStyle}>
      {bgInfo.url && <div className="absolute inset-0 z-0 bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md" style={{ opacity: 1 - bgInfo.opacity }}></div>}
      <div className="relative z-10 min-h-screen flex flex-col pt-0">
        <AnimatePresence mode="wait">
          {!user ? (
            <AuthScreen key="auth" onLogin={handleLoginSuccess} />
          ) : (
            <MainLayout key="main" user={user} onUserUpdate={setUser} onLogout={handleLogout} isDark={isDark} setIsDark={setIsDark} />
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function AuthScreen({ onLogin }) {
  const [mode, setMode] = useState("login"); // login | register | reset
  const isLogin = mode === "login";
  const isRegister = mode === "register";
  const isReset = mode === "reset";
  const [formData, setFormData] = useState({ student_id: "", password: "", email: "", verification_code: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [registerConfig, setRegisterConfig] = useState({ email_verification_required: false, email_service_enabled: false });
  const [sendingCode, setSendingCode] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    api.getRegisterConfig()
      .then((res) => setRegisterConfig(res.data || { email_verification_required: false, email_service_enabled: false }))
      .catch(() => setRegisterConfig({ email_verification_required: false, email_service_enabled: false }));
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setNotice("");
    setIsLoading(true);
    try {
      if (isReset) {
        await api.resetPassword({
          student_id: formData.student_id,
          email: formData.email,
          verification_code: formData.verification_code,
          new_password: formData.password,
        });
        setNotice("密码已重置，请使用新密码登录");
        setMode("login");
        setFormData((value) => ({ ...value, password: "", verification_code: "" }));
        return;
      }

      const action = isLogin ? api.login : api.register;
      await action(formData);
      const res = await api.checkAuth();
      onLogin(res.data);
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.detail || "Authentication request failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendCode = async () => {
    setError("");
    setNotice("");
    if (isReset && !formData.student_id) {
      setError("请先输入账号 ID");
      return;
    }
    if (!formData.email) {
      setError("请先输入邮箱");
      return;
    }
    setSendingCode(true);
    try {
      if (isReset) {
        await api.sendResetPasswordEmailCode({ student_id: formData.student_id, email: formData.email });
        setNotice("验证码已发送，请在 10 分钟内完成重置");
      } else {
        await api.sendEmailCode(formData.email);
        setNotice("验证码已发送，请在 10 分钟内完成注册");
      }
      setCooldown(60);
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.detail || "验证码发送失败");
    } finally {
      setSendingCode(false);
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md"
    >
      <motion.div 
        layoutId="auth-card"
        className="w-full max-w-md bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border border-slate-200 dark:border-slate-800 p-8 rounded-3xl shadow-2xl relative z-10"
      >
        <div className="text-center mb-8 flex flex-col items-center">
          <div className="inline-flex rounded-2xl mb-4">
             <img src={logoImg} alt="Nexus Logo" className="w-28 h-28 object-contain drop-shadow-xl dark:opacity-100 transition-transform duration-500 hover:scale-110" />
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight">
            {isLogin ? "欢迎回来" : isReset ? "找回密码" : "创建账户"}
          </h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            {isLogin ? "登录此账户以访问面板" : isReset ? "通过邮箱验证码重置密码" : "注册以获取API密钥"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <AnimatePresence>
            {error && (
              <motion.div 
                initial={{ opacity: 0, y: -10, height: 0 }} animate={{ opacity: 1, y: 0, height: 'auto' }} exit={{ opacity: 0, y: -10, height: 0 }}
                className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl flex items-center text-sm"
              >
                <AlertCircle size={16} className="mr-2 shrink-0" /> {error}
              </motion.div>
            )}
          </AnimatePresence>
          <AnimatePresence>
            {notice && (
              <motion.div
                initial={{ opacity: 0, y: -10, height: 0 }} animate={{ opacity: 1, y: 0, height: 'auto' }} exit={{ opacity: 0, y: -10, height: 0 }}
                className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-400 px-4 py-3 rounded-xl flex items-center text-sm"
              >
                <CheckCircle2 size={16} className="mr-2 shrink-0" /> {notice}
              </motion.div>
            )}
          </AnimatePresence>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">账号 ID</label>
              <input
                type="text" required
                className="w-full px-4 py-3 rounded-xl bg-slate-100 dark:bg-slate-950 border border-transparent focus:border-slate-500 focus:bg-white dark:focus:bg-slate-900 outline-none transition-all placeholder:text-slate-400"
                placeholder="例如: user_123"
                value={formData.student_id} onChange={e => setFormData({...formData, student_id: e.target.value})}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">{isReset ? "新密码" : "密码"}</label>
              <input
                type="password" required
                className="w-full px-4 py-3 rounded-xl bg-slate-100 dark:bg-slate-950 border border-transparent focus:border-slate-500 focus:bg-white dark:focus:bg-slate-900 outline-none transition-all placeholder:text-slate-400"
                placeholder={isReset ? "不少于6位" : "••••••••"}
                value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})}
              />
            </div>
            {((isRegister && registerConfig.email_verification_required) || isReset) && (
              <>
                <div className="space-y-1.5">
                  <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">邮箱</label>
                  <div className="flex gap-2">
                    <input
                      type="email" required
                      className="flex-1 px-4 py-3 rounded-xl bg-slate-100 dark:bg-slate-950 border border-transparent focus:border-slate-500 focus:bg-white dark:focus:bg-slate-900 outline-none transition-all placeholder:text-slate-400"
                      placeholder="you@example.com"
                      value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})}
                    />
                    <button
                      type="button"
                      onClick={handleSendCode}
                      disabled={sendingCode || cooldown > 0}
                      className="shrink-0 px-4 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-400 text-white text-sm font-semibold transition-colors"
                    >
                      {sendingCode ? "发送中..." : cooldown > 0 ? `${cooldown}s` : "发送验证码"}
                    </button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">邮箱验证码</label>
                  <input
                    type="text" inputMode="numeric" pattern="[0-9]*" maxLength={6} required
                    className="w-full px-4 py-3 rounded-xl bg-slate-100 dark:bg-slate-950 border border-transparent focus:border-slate-500 focus:bg-white dark:focus:bg-slate-900 outline-none transition-all placeholder:text-slate-400 tracking-[0.3em]"
                    placeholder="123456"
                    value={formData.verification_code} onChange={e => setFormData({...formData, verification_code: e.target.value.replace(/\\D/g, '').slice(0, 6)})}
                  />
                </div>
              </>
            )}
          </div>

          <button
            type="submit" disabled={isLoading}
            className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 text-white font-semibold rounded-xl transition-colors flex justify-center items-center gap-2 shadow-lg"
          >
            {isLoading && <Activity size={18} className="animate-spin" />}
            {isLogin ? "登录" : isReset ? "重置密码" : registerConfig.email_verification_required ? "验证并注册" : "注册"}
          </button>
        </form>

        <div className="mt-8 text-center">
          {isLogin && (
            <div className="space-y-2">
              <button
                onClick={() => { setMode("register"); setError(""); setNotice(""); }}
                className="text-sm text-slate-600 dark:text-slate-400 hover:underline font-medium"
              >
                还没有账号？去注册
              </button>
              <div>
                <button
                  onClick={() => { setMode("reset"); setError(""); setNotice(""); }}
                  className="text-sm text-slate-600 dark:text-slate-400 hover:underline font-medium"
                >
                  忘记密码？找回
                </button>
              </div>
            </div>
          )}
          {isRegister && (
            <button
              onClick={() => { setMode("login"); setError(""); setNotice(""); }}
              className="text-sm text-slate-600 dark:text-slate-400 hover:underline font-medium"
            >
              已有账号？去登录
            </button>
          )}
          {isReset && (
            <button
              onClick={() => { setMode("login"); setError(""); setNotice(""); }}
              className="text-sm text-slate-600 dark:text-slate-400 hover:underline font-medium"
            >
              返回登录
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function MainLayout({ user, onUserUpdate, onLogout, isDark, setIsDark }) {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const tabs = [
    { id: "dashboard", label: "概览", icon: LayoutDashboard },
    { id: "marketplace", label: "模型广场", icon: Target },
    { id: "keys", label: "密钥管理", icon: Key },
    { id: "logs", label: "调用日志", icon: HistoryIcon },
    { id: "game", label: "世界", icon: Gamepad2 },
    { id: "settings", label: "用户设置", icon: User },
  ];
  const isAdmin = user?.student_id === "admin" || user?.student_id === "root";

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex min-h-screen">
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div 
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 bg-black/50 z-40 lg:hidden backdrop-blur-sm"
          />
        )}
      </AnimatePresence>

      <motion.aside 
        className={`fixed lg:sticky top-0 h-screen ${isCollapsed ? "w-20" : "w-64"} bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border-r border-slate-200 dark:border-slate-800 z-50 flex flex-col transition-all duration-300 lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="relative flex items-center justify-center p-6 pb-4 h-20 shrink-0">
            <span className={`font-extrabold tracking-tight text-slate-800 dark:text-white transition-all duration-300 ${isCollapsed ? "text-2xl" : "text-2xl"}`}>
              {isCollapsed ? "N" : "NEXUS"}
            </span>
            <button 
              onClick={() => setIsCollapsed(!isCollapsed)} 
              className="hidden lg:flex absolute -right-3 top-7 items-center justify-center w-6 h-6 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-full text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 shadow-sm z-50 transition-colors"
            >
              {isCollapsed ? <ChevronRight size={14}/> : <ChevronLeft size={14}/>}
            </button>
            <button onClick={() => setSidebarOpen(false)} className="lg:hidden absolute right-4 p-1 text-slate-500 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
              <X size={20} />
            </button>
          </div>

        <nav className="flex-1 px-4 space-y-2 mt-4 overflow-y-auto">
          {tabs.map(tab => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); setSidebarOpen(false); }}
                className={`w-full flex items-center ${isCollapsed ? "justify-center px-0" : "gap-3 px-4"} py-3 rounded-xl transition-all duration-200 ${isActive ? "bg-slate-800 text-white shadow-md" : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50"}`}
              >
                <tab.icon size={20} className={isActive ? "text-slate-100" : "text-slate-400"} />
                {!isCollapsed && <span className="font-semibold text-sm">{tab.label}</span>}
              </button>
            )
          })}
          <button
            onClick={() => { window.location.href = "/playground/"; }}
            className={`w-full flex items-center ${isCollapsed ? "justify-center px-0" : "gap-3 px-4"} py-3 rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 transition-all`}
          >
            <ImageIcon size={20} className="text-slate-400" />
            {!isCollapsed && <span className="font-semibold text-sm">图像工坊</span>}
          </button>
          {isAdmin && (
            <div className="pt-6 mt-6 border-t border-slate-200 dark:border-slate-800">
              <p className={`px-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3 ${isCollapsed ? "text-center" : ""}`}>{isCollapsed ? "ADMIN" : "管理员"}</p>
              <button onClick={() => window.open("/admin", "_blank")} className={`w-full flex items-center ${isCollapsed ? "justify-center px-0" : "gap-3 px-4"} py-3 rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 transition-all font-semibold text-sm`}>
                <Settings size={20} className="text-slate-400" />
                {!isCollapsed && <span>管理面板</span>}
              </button>
            </div>
          )}
        </nav>

        <div
          onClick={() => setActiveTab("settings")}
          className={`${isCollapsed ? "p-2 m-2" : "p-4 m-4"} bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md rounded-2xl border border-slate-200 dark:border-slate-800 transition-all duration-300 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800/50`}
          title="账号设置"
        >
          <div className={`flex items-center ${isCollapsed ? "justify-center" : "gap-3"} overflow-hidden ${isCollapsed ? "mb-3" : "mb-4"}`}>
              {user?.avatar ? (
                <img src={`/static/${user.avatar}`} alt="" className="w-9 h-9 rounded-full object-cover shrink-0" />
              ) : (
                <div className="w-9 h-9 rounded-full bg-slate-800 dark:bg-slate-700 flex items-center justify-center text-white font-bold shrink-0">
                  {(user?.display_name || user?.student_id || "U")[0].toUpperCase()}
                </div>
              )}
              {!isCollapsed && (
                <div className="truncate">
                  <p className="text-sm font-bold truncate dark:text-slate-200">{user?.display_name || user?.student_id}</p>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase font-semibold">用户</p>
                </div>
              )}
            </div>
          
          <div className={`flex ${isCollapsed ? "flex-col items-center" : ""} gap-2`}>
              <button 
                onClick={() => setIsDark(!isDark)} 
                className={`${isCollapsed ? "w-10 h-10 shrink-0" : "flex-1 py-2"} flex justify-center items-center bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border border-slate-200 dark:border-slate-700 rounded-xl text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors`}
              >
                {isDark ? <Sun size={16} /> : <Moon size={16} />}
              </button>
              <button 
                onClick={onLogout} 
                className={`${isCollapsed ? "w-10 h-10 shrink-0" : "flex-1 py-2"} flex justify-center items-center bg-red-50 dark:bg-red-500/10 border border-red-100 dark:border-red-500/20 rounded-xl text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors`} 
                title="退出登录"
              >
                <LogOut size={16} className={isCollapsed ? "ml-0.5" : ""} />
              </button>
            </div>
        </div>
      </motion.aside>

      <main className="flex-1 flex flex-col min-w-0">
        <header className="lg:hidden flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md sticky top-0 z-30">
          <div className="flex items-center gap-2 font-extrabold text-slate-800 dark:text-slate-200 text-xl tracking-tight">
            <div className="flex items-center justify-center rounded">
               
            </div>
            <span className="text-slate-800 dark:text-white">NEXUS</span>
          </div>
          <button onClick={() => setSidebarOpen(true)} className="p-2 -mr-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">
            <Menu size={24} />
          </button>
        </header>

        <div className="p-6 md:p-10 flex-1 max-w-6xl mx-auto w-full">
          <AnimatePresence mode="wait">
            {activeTab === "dashboard" && <Dashboard key="dashboard" user={user} setActiveTab={setActiveTab} />}
            {activeTab === "marketplace" && <MarketplaceView key="marketplace" />}
            {activeTab === "keys" && <KeysManager key="keys" />}
            {activeTab === "logs" && <LogsView key="logs" />}
            {activeTab === "game" && <GameModule key="game" user={user} api={api} />}
            {activeTab === "settings" && <UserSettings key="settings" user={user} onUserUpdate={onUserUpdate} />}
          </AnimatePresence>
        </div>
      </main>
    </motion.div>
  );
}

function Dashboard({ user, setActiveTab }) {
  const [data, setData] = useState(null);
  const [checkin, setCheckin] = useState(null);
  const [toast, setToast] = useState(null);
  const [balanceHistory, setBalanceHistory] = useState([]);
  const [visibleCurves, setVisibleCurves] = useState(["total"]);
  
  // Promo popup
  const [promoDismissed, setPromoDismissed] = useState(() => localStorage.getItem("opus_promo_dismissed") === "true");
  const dismissPromo = () => { setPromoDismissed(true); localStorage.setItem("opus_promo_dismissed", "true"); };

  // Modals state
  const [showDetails, setShowDetails] = useState(false);
  const [hists, setHists] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);

  const showToast = (msg, type) => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 2500);
  };
  
  useEffect(() => { 
    api.getDashboard().then(res => setData(res.data)).catch(console.error); 
    api.checkinStatus().then(res => setCheckin(res.data)).catch(console.error);
    axios.get("/api/balance-history?limit=200").then(res => setBalanceHistory(res.data.points || [])).catch(console.error);
  }, []);

  useEffect(() => {
    if (showDetails) {
      document.body.style.paddingRight = `${window.innerWidth - document.documentElement.clientWidth}px`;
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    };
  }, [showDetails]);

  useEffect(() => {
    if (showDetails) {
      document.body.style.paddingRight = `${window.innerWidth - document.documentElement.clientWidth}px`;
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    };
  }, [showDetails]);

  const handleCheckin = async () => {
    try {
      const res = await api.doCheckin();
      const checkinResult = res.data || {};
      const rewardUsd = checkinResult.usd_awarded ?? 0;

      if (checkinResult.ok === false) {
        showToast(checkinResult.error || "今日已签到", "error");
        api.checkinStatus().then(res => setCheckin(res.data)).catch(console.error);
        return;
      }

      showToast(`签到成功！余额 +${formatUsd(rewardUsd)}`, "success");
      api.getDashboard().then(res => setData(res.data)).catch(console.error);
      api.checkinStatus().then(res => setCheckin(res.data)).catch(console.error);
      axios.get("/api/balance-history?limit=200").then(res => setBalanceHistory(res.data.points || [])).catch(console.error);
    } catch(e) {
      showToast(e.response?.data?.detail || "签到失败", "error");
    }
  };

  const loadDetails = async () => {
    try {
      const [hRes, lRes] = await Promise.all([api.getCheckinHistory(), api.getCheckinLeaderboard()]);
      setHists(hRes.data.history || []);
      setLeaderboard(lRes.data.leaderboard || []);
      setShowDetails(true);
    } catch (e) {
      showToast("加载签到详情失败", "error");
    }
  };

  const stats = [
    { title: "当前余额", value: formatUsd(data?.balance_usd), icon: CreditCard, color: "text-emerald-500", bg: "bg-emerald-500/10", subValue: "按美元余额扣费" },
    { title: "累计消费", value: formatUsd(data?.total_cost_usd), icon: Activity, color: "text-slate-600", bg: "bg-slate-500/10", subValue: `${data?.request_count?.toLocaleString() || "0"} 次请求` },
    { title: "今日消费", value: formatUsd(data?.today_cost_usd), icon: Zap, color: "text-rose-500", bg: "bg-rose-500/10", subValue: `${data?.usd_request_count?.toLocaleString() || "0"} 次计费请求` },
    { 
      title: "模型状态", 
      value: "正常", 
      icon: CheckCircle2, color: "text-indigo-500", bg: "bg-indigo-500/10",
      subValue: `Claude / Kimi / MIMO / GPT 可用`
    }
  ];

  const balanceCurveConfig = [
    { key: "total", label: "余额", color: "#6366f1", dataKey: "balance_after_usd", yAxisId: "balance" },
    { key: "spend", label: "消耗", color: "#ef4444", dataKey: "spend_window_cumulative_usd", yAxisId: "delta" },
    { key: "checkin", label: "签到", color: "#10b981", dataKey: "checkin_window_cumulative_usd", yAxisId: "delta" },
    { key: "welfare", label: "福利", color: "#f59e0b", dataKey: "welfare_window_cumulative_usd", yAxisId: "delta" },
  ];

  const chartData = balanceHistory.map((point, index) => {
    const firstPoint = balanceHistory[0] || {};
    const previousPoint = index > 0 ? balanceHistory[index - 1] : null;
    const spendBase = Number(firstPoint.spend_cumulative_usd || 0);
    const checkinBase = Number(firstPoint.checkin_cumulative_usd || 0);
    const welfareBase = Number(firstPoint.welfare_cumulative_usd || 0);

    return {
      ...point,
      time: formatBalanceChartTick(point.timestamp, previousPoint?.timestamp),
      spend_window_cumulative_usd: Number(point.spend_cumulative_usd || 0) - spendBase,
      checkin_window_cumulative_usd: Number(point.checkin_cumulative_usd || 0) - checkinBase,
      welfare_window_cumulative_usd: Number(point.welfare_cumulative_usd || 0) - welfareBase,
    };
  });

  const toggleCurve = (key) => {
    setVisibleCurves((prev) => prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-8 relative">
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -20, x: "-50%" }} animate={{ opacity: 1, y: 0, x: "-50%" }} exit={{ opacity: 0, y: -20, x: "-50%" }} className={`fixed top-6 left-1/2 z-[100] px-4 py-3 rounded-2xl flex items-center shadow-2xl border ${ toast.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400" }`}>
            <span className="font-medium text-sm">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {user && !user.email && (
          <motion.div
            initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-2xl px-5 py-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              <AlertCircle size={20} className="text-amber-500 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">您还未绑定邮箱</p>
                <p className="text-xs text-amber-600 dark:text-amber-400">绑定邮箱可在忘记密码时找回账号，建议立即绑定</p>
              </div>
            </div>
            <button
              onClick={() => setActiveTab("settings")}
              className="shrink-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              去绑定
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {!promoDismissed && user && (
          <motion.div
            initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            className="relative bg-gradient-to-r from-purple-500/10 via-pink-500/10 to-amber-500/10 dark:from-purple-500/20 dark:via-pink-500/20 dark:to-amber-500/20 border border-purple-300 dark:border-purple-500/30 rounded-2xl px-5 py-4 overflow-hidden"
          >
            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PHBhdHRlcm4gaWQ9ImRvdHMiIHg9IjAiIHk9IjAiIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjEiIGZpbGw9InJnYmEoMTY4LCA4NSwgMjQ3LCAwLjA4KSIvPjwvcGF0dGVybj48L2RlZnM+PHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0idXJsKCNkb3RzKSIvPjwvc3ZnPg==')] opacity-60" />
            <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl shadow-lg shadow-purple-500/20">
                  <Zap size={20} className="text-white" />
                </div>
                <div>
                  <p className="text-sm font-bold text-purple-800 dark:text-purple-200">
                    Opus 上新特惠
                    <span className="ml-2 inline-block px-2 py-0.5 text-[10px] font-bold bg-purple-500 text-white rounded-full animate-pulse">限时</span>
                  </p>
                  <p className="text-xs text-purple-600 dark:text-purple-300 mt-0.5">
                    Claude Opus 4.6 / 4.7 限时 0.4 倍率促销，5 月 9 日 – 12 日
                  </p>
                </div>
              </div>
              <button
                onClick={dismissPromo}
                className="shrink-0 px-3 py-1.5 text-xs font-medium text-purple-500 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-200 hover:bg-purple-100 dark:hover:bg-purple-500/10 rounded-lg transition-colors"
              >
                知道了
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }} className="bg-white/50 dark:bg-slate-900/50 backdrop-blur-xl border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-slate-500 flex items-center gap-2">
                {stat.title}
              </span>
              <div className={`p-2.5 rounded-xl ${stat.bg} ${stat.color}`}>
                <stat.icon size={20} strokeWidth={2.5} />
              </div>
            </div>
            <div className="flex items-baseline gap-2 w-full overflow-hidden">
              <span className={`text-3xl font-bold tracking-tight truncate ${stat.color}`} title={stat.value?.toString()}>{stat.value}</span>
            </div>
            {stat.subValue && <div className="mt-2 text-xs text-slate-400">{stat.subValue}</div>}
          </motion.div>
        ))}
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="bg-white/50 dark:bg-slate-900/50 backdrop-blur-xl border border-slate-200 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
        <div className="p-6 md:p-8 flex flex-col md:flex-row items-center justify-between gap-6 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/5 via-teal-500/5 to-cyan-500/5" />
          <div className="relative z-10 text-center md:text-left">
            <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center justify-center md:justify-start gap-3">
              <CheckCircle2 className="text-emerald-500" size={28} />
              每日签到
            </h2>
            <p className="text-slate-500 text-sm mt-2 font-medium">领取每日余额奖励</p>
          </div>
          <div className="relative z-10 flex flex-col items-center sm:flex-row gap-4">
            <span className="text-sm font-medium text-slate-500 bg-white/50 dark:bg-slate-800/50 px-4 py-2 rounded-xl backdrop-blur-md border border-slate-200 dark:border-slate-700">
              今日状态：<span className={checkin?.checked_in ? "text-emerald-500 font-bold" : "text-amber-500 font-bold"}>{checkin?.checked_in ? "已签到" : "未签到"}</span>
            </span>
            {!checkin?.checked_in ? (
              <button onClick={handleCheckin} className="group relative px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white font-medium shadow-xl shadow-emerald-500/20 active:scale-95 transition-all overflow-hidden">
                <span className="relative z-10 flex items-center justify-center gap-2">点我签到</span>
              </button>
            ) : (
              <button disabled className="px-6 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 font-medium cursor-not-allowed">明日再来</button>
            )}
            {checkin?.checked_in && (
              <button onClick={loadDetails} className="px-5 py-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-500/10 hover:bg-indigo-100 text-indigo-600 dark:text-indigo-400 font-medium transition-all shadow-sm">
                签到详情
              </button>
            )}
          </div>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }} className="bg-white/50 dark:bg-slate-900/50 backdrop-blur-xl border border-slate-200 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
        <div className="p-6 md:p-8 space-y-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100">额度变化曲线</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">展示签到、福利发放和消耗带来的余额变化。</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {balanceCurveConfig.map((curve) => {
                const active = visibleCurves.includes(curve.key);
                return (
                  <button
                    key={curve.key}
                    onClick={() => toggleCurve(curve.key)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${active ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900" : "border-slate-200 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"}`}
                  >
                    {curve.label}
                  </button>
                );
              })}
            </div>
          </div>
          {chartData.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 p-10 text-center text-sm text-slate-400 dark:border-slate-700">暂无额度变化记录</div>
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" strokeOpacity={0.2} />
                  <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} dy={10} minTickGap={24} />
                  <YAxis
                    yAxisId="balance"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 10, fill: '#64748b' }}
                    dx={-10}
                    tickFormatter={(value) => formatUsd(value)}
                  />
                  <YAxis
                    yAxisId="delta"
                    orientation="right"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickFormatter={(value) => formatUsd(value)}
                  />
                  <Tooltip
                    formatter={(value) => formatUsd(value)}
                    labelFormatter={(_, payload) => formatBalanceChartTooltipLabel(payload?.[0]?.payload?.timestamp)}
                    contentStyle={{ backgroundColor: '#0f172a', borderRadius: '12px', border: 'none', color: '#fff', fontSize: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                  />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                  {balanceCurveConfig.filter((curve) => visibleCurves.includes(curve.key)).map((curve) => (
                    <Area
                      key={curve.key}
                      type="monotone"
                      name={curve.label}
                      dataKey={curve.dataKey}
                      yAxisId={curve.yAxisId}
                      stroke={curve.color}
                      fill={curve.color}
                      fillOpacity={0.12}
                      strokeWidth={3}
                      connectNulls
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </motion.div>

      {/* API Configuration Card */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="bg-gradient-to-br from-indigo-500/[0.02] to-blue-500/[0.02] backdrop-blur-xl border border-indigo-500/10 rounded-3xl overflow-hidden shadow-sm">
        <div className="p-6 md:p-8">
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2 mb-4">
            <Zap className="text-indigo-500" size={20} />
            客户端接口配置
          </h3>
          <div className="bg-white/60 dark:bg-slate-900/60 rounded-2xl p-5 border border-slate-200/50 dark:border-slate-800/50">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex flex-col">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">BASE URL 地址（中转与外网代理）</span>
                <code className="text-indigo-600 dark:text-indigo-400 font-mono text-sm sm:text-base font-medium select-all">
                  https://portal.wbuai.me/v1
                </code>
              </div>
              <button onClick={() => { navigator.clipboard.writeText("https://portal.wbuai.me/v1"); showToast("已复制 URL！", "success"); }} className="flex items-center gap-2 px-4 py-2 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 font-medium rounded-xl transition-colors shrink-0">
                <Copy size={16} /> 复制 URL
              </button>
            </div>
            <p className="text-xs text-slate-500 mt-4 leading-relaxed">
              请在兼容 OpenAI 或 Anthropic Claude 格式的客户端（如 NextChat, LobeChat, ChatBox）中填入以上接口地址与您分配的 Key。如果默认报错请确保末尾包含了 <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded">/v1</code> 路径。当前已开放 Claude、Kimi、MIMO 与 GPT。
            </p>
          </div>
        </div>
      </motion.div>

      {/* Checkin Details Modal */}
      <AnimatePresence>
        {showDetails && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm sm:p-6">
            <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
              <div className="px-6 py-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-950/50">
                <h3 className="text-xl font-bold flex items-center gap-2 text-slate-800 dark:text-slate-100">
                  <Calendar className="text-indigo-500" size={24} /> 签到详情
                </h3>
                <button onClick={() => setShowDetails(false)} className="p-2 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-full text-slate-400 transition-colors">
                  <X size={20} />
                </button>
              </div>

              <div className="p-6 overflow-y-auto flex-1 bg-slate-50 dark:bg-[#0B1120]">
                <div className="grid md:grid-cols-2 gap-8">
                  {/* Leaderboard Section */}
                  <div>
                    <h4 className="text-sm font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2 mb-4">
                      <Trophy size={16} className="text-amber-500" /> 今日签到榜 (Top 30)
                    </h4>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                      {leaderboard.length === 0 ? (
                        <div className="p-8 text-center text-slate-400 text-sm">暂无签到数据</div>
                      ) : (
                        <div className="divide-y divide-slate-100 dark:divide-slate-800 h-96 overflow-y-auto">
                          {leaderboard.map((item, idx) => (
                            <div key={idx} className="flex items-center justify-between p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                              <div className="flex items-center gap-3">
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${idx === 0 ? 'bg-amber-100 text-amber-600' : idx === 1 ? 'bg-slate-200 text-slate-600' : idx === 2 ? 'bg-orange-100 text-orange-600' : 'bg-slate-100 dark:bg-slate-800 text-slate-400'}`}>
                                  {idx + 1}
                                </div>
                                <span className="font-medium text-sm text-slate-700 dark:text-slate-200 truncate max-w-[100px] sm:max-w-[150px]" title={item.display_name}>{item.display_name}</span>
                              </div>
                              <span className="text-emerald-500 font-bold font-mono whitespace-nowrap shrink-0">{formatUsd(item.usd_awarded || 0)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* History Section */}
                  <div>
                    <h4 className="text-sm font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2 mb-4">
                      <HistoryIcon size={16} className="text-indigo-500" /> 我的签到历史
                    </h4>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                      {hists.length === 0 ? (
                        <div className="p-8 text-center text-slate-400 text-sm">暂无历史记录</div>
                      ) : (
                        <div className="divide-y divide-slate-100 dark:divide-slate-800 h-96 overflow-y-auto">
                          {hists.map((item, idx) => (
                            <div key={idx} className="flex items-center justify-between p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                              <span className="text-slate-500 text-sm font-mono">{item.checkin_date}</span>
                              <span className="text-emerald-500 font-bold font-mono">{formatUsd(item.usd_awarded || 0)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </motion.div>
  );
}

function MarketplaceView() {
  const [marketplace, setMarketplace] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedModelId, setSelectedModelId] = useState(null);
  const [toast, setToast] = useState(null);
  const toastTimerRef = useRef(null);

  useEffect(() => {
    loadMarketplacePayload()
      .then((payload) => {
        setMarketplace(payload);
        setSelectedModelId(payload.models?.[0]?.id || null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const models = marketplace?.models || [];
  const pricing = marketplace?.pricing || {};
  const notes = pricing.notes || [];
  const selectedModel = models.find((model) => model.id === selectedModelId) || models[0] || null;

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => setToast(null), 2200);
  };

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  const copyText = async (value, label) => {
    try {
      await navigator.clipboard.writeText(value);
      showToast(`已复制${label}`, "success");
    } catch (error) {
      showToast(`复制${label}失败`, "error");
    }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-8">
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -20, x: "-50%" }} animate={{ opacity: 1, y: 0, x: "-50%" }} exit={{ opacity: 0, y: -20, x: "-50%" }} className={`fixed top-6 left-1/2 z-[100] px-4 py-3 rounded-2xl flex items-center shadow-2xl border ${toast.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400"}`}>
            <span className="font-medium text-sm">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <header>
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-800 dark:text-slate-100">模型广场</h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">左侧选择模型，右侧查看模型 ID、上下文、输出上限和官方价格。</p>
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,0.9fr)]">
        <section className="space-y-4">
          {isLoading ? (
            <div className="flex min-h-[240px] items-center justify-center rounded-3xl border border-slate-200 bg-white/70 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70">
              <Activity className="animate-spin text-indigo-500" size={28} />
            </div>
          ) : models.length === 0 ? (
            <div className="rounded-3xl border border-slate-200 bg-white/70 p-8 text-center text-slate-500 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-400">
              暂无可用模型
            </div>
          ) : (
            models.map((model) => {
              const isSelected = selectedModel?.id === model.id;
              return (
                <div
                  key={model.id}
                  onClick={() => setSelectedModelId(model.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedModelId(model.id);
                    }
                  }}
                  className={`overflow-hidden rounded-3xl border backdrop-blur-xl transition-all ${
                    isSelected
                      ? "border-indigo-300/80 bg-white/80 shadow-lg shadow-indigo-500/10 dark:border-indigo-500/30 dark:bg-slate-900/80"
                      : "border-slate-200 bg-white/60 hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900/60 dark:hover:border-slate-700"
                  }`}
                >
                  <div className="flex w-full items-center justify-between gap-4 p-5 text-left">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.2em] text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
                          {model.family}
                        </span>
                        <span className="text-lg font-bold text-slate-800 dark:text-slate-100">{model.display_name || model.id}</span>
                      </div>
                      <p className="mt-2 text-sm font-mono text-slate-500 dark:text-slate-400">{model.id}</p>
                      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{model.description}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          copyText(model.id, "模型 ID");
                        }}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-300 dark:hover:bg-slate-800"
                      >
                        <Copy size={14} />
                        复制 ID
                      </button>
                      <div className="hidden rounded-2xl bg-slate-100/90 px-3 py-2 text-right text-xs text-slate-500 dark:bg-slate-800/80 dark:text-slate-300 sm:block">
                        <div>上下文 {model.context_window?.toLocaleString?.() || model.context_window}</div>
                        <div>输出 {model.max_output_tokens?.toLocaleString?.() || model.max_output_tokens}</div>
                      </div>
                      <ChevronDown className={`text-slate-400 transition-transform ${isSelected ? "-rotate-90" : "rotate-90"}`} size={20} />
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </section>

        <aside className="space-y-4">
          <div className="rounded-3xl border border-slate-200 bg-white/70 p-6 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl bg-indigo-50 p-3 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
                <Target size={20} />
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-500 dark:text-slate-400">总览</div>
                <div className="text-lg font-bold text-slate-800 dark:text-slate-100">{models.length} 个模型可用</div>
              </div>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-slate-500 dark:text-slate-400">选择左侧模型后，可以直接复制模型 ID，并查看当前模型的上下文与价格。</p>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white/70 p-6 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70">
            {!selectedModel ? (
              <div className="text-sm text-slate-500 dark:text-slate-400">暂无模型详情</div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-500 dark:text-slate-400">当前模型</div>
                    <div className="mt-1 text-xl font-bold text-slate-800 dark:text-slate-100">{selectedModel.display_name || selectedModel.id}</div>
                    <div className="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400 break-all">{selectedModel.id}</div>
                  </div>
                  <button
                    onClick={() => copyText(selectedModel.id, "模型 ID")}
                    className="inline-flex items-center gap-2 rounded-xl bg-indigo-50 px-3 py-2 text-xs font-semibold text-indigo-600 transition-colors hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20"
                  >
                    <Copy size={14} />
                    复制
                  </button>
                </div>

                <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-950/60">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Context</div>
                    <div className="mt-2 text-lg font-bold text-slate-800 dark:text-slate-100">{selectedModel.context_window?.toLocaleString?.() || selectedModel.context_window}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-950/60">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Max Output</div>
                    <div className="mt-2 text-lg font-bold text-slate-800 dark:text-slate-100">{selectedModel.max_output_tokens?.toLocaleString?.() || selectedModel.max_output_tokens}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-950/60">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">计费单位</div>
                    <div className="mt-2 text-lg font-bold text-slate-800 dark:text-slate-100">USD / 1M Tokens</div>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-950/60">
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">官方价格</div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl bg-slate-900 px-3 py-3 text-xs text-indigo-200">
                      <div className="text-slate-400">输入</div>
                      <div className="mt-1 text-sm font-semibold text-white">{formatPricePer1M(selectedModel?.pricing_usd?.input)}</div>
                    </div>
                    <div className="rounded-xl bg-slate-900 px-3 py-3 text-xs text-indigo-200">
                      <div className="text-slate-400">输出</div>
                      <div className="mt-1 text-sm font-semibold text-white">{formatPricePer1M(selectedModel?.pricing_usd?.output)}</div>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="text-sm font-semibold text-slate-500 dark:text-slate-400">缓存与换算</div>
                  {[
                    { name: "Cache Write", value: selectedModel?.pricing_usd?.cache_write, note: "缓存写入价格（若模型支持）" },
                    { name: "Cache Read", value: selectedModel?.pricing_usd?.cache_read, note: "缓存命中价格（若模型支持）" },
                  ].map((rule) => (
                    <div key={rule.name} className="rounded-2xl border border-slate-200 bg-white/80 p-4 dark:border-slate-800 dark:bg-slate-900/50">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">{rule.name}</span>
                        <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300">{formatPricePer1M(rule.value)}</span>
                      </div>
                      {rule.note && <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{rule.note}</p>}
                    </div>
                  ))}
                </div>

                {selectedModel?.pricing_native && (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-950/60">
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">官方原币价格</div>
                    <div className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                      币种：{selectedModel.pricing_native.currency}
                    </div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs dark:border-slate-800 dark:bg-slate-900/50">
                        输入：{selectedModel.pricing_native.input} {selectedModel.pricing_native.currency} / 1M
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs dark:border-slate-800 dark:bg-slate-900/50">
                        输出：{selectedModel.pricing_native.output} {selectedModel.pricing_native.currency} / 1M
                      </div>
                    </div>
                  </div>
                )}

                {(selectedModel.variants || []).length > 0 && (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-950/60">
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">可用路由</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedModel.variants.map((variant) => (
                        <button
                          key={variant}
                          onClick={() => copyText(variant, "模型路由")}
                          className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-mono text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                        >
                          {variant}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

              </div>
            )}
          </div>
        </aside>
      </div>
    </motion.div>
  );
}

function UserSettings({ user, onUserUpdate }) {
  // -- Profile state --
  const [displayName, setDisplayName] = useState(user?.display_name || "");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [avatarFile, setAvatarFile] = useState(null);
  const [avatarPreview, setAvatarPreview] = useState(user?.avatar ? `/static/${user.avatar}` : null);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [showCrop, setShowCrop] = useState(false);
  const [cropSrc, setCropSrc] = useState(null);
  const [cropScale, setCropScale] = useState(1);
  const [cropX, setCropX] = useState(0);
  const [cropY, setCropY] = useState(0);
  const [cropDragging, setCropDragging] = useState(false);
  const [cropDragStart, setCropDragStart] = useState({ x: 0, y: 0 });
  const fileInputRef = useRef(null);
  const cropCanvasRef = useRef(null);

  // -- Email state --
  const [emailForm, setEmailForm] = useState({ email: user?.email || "", verification_code: "" });
  const [passwordForm, setPasswordForm] = useState({ current_password: "", new_password: "", confirm_password: "", verification_code: "" });
  const [registerConfig, setRegisterConfig] = useState({ email_verification_required: false });
  const [sendingCode, setSendingCode] = useState(false);
  const [pwdSendingCode, setPwdSendingCode] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [pwdCooldown, setPwdCooldown] = useState(0);
  const [toast, setToast] = useState(null);

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 2600);
  };

  useEffect(() => {
    api.getRegisterConfig()
      .then((res) => setRegisterConfig(res.data || { email_verification_required: false }))
      .catch(() => setRegisterConfig({ email_verification_required: false }));
  }, []);

  useEffect(() => {
    setEmailForm((value) => ({ ...value, email: user?.email || "" }));
  }, [user?.email]);

  useEffect(() => {
    setDisplayName(user?.display_name || "");
  }, [user?.display_name]);

  useEffect(() => {
    if (user?.avatar) setAvatarPreview(`/static/${user.avatar}`);
  }, [user?.avatar]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  useEffect(() => {
    if (pwdCooldown <= 0) return;
    const timer = window.setTimeout(() => setPwdCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [pwdCooldown]);

  // Clamp crop position when scale changes
  useEffect(() => {
    const maxOffset = 224 * (cropScale - 1);
    setCropX(x => Math.min(0, Math.max(-maxOffset, x)));
    setCropY(y => Math.min(0, Math.max(-maxOffset, y)));
  }, [cropScale]);

  // -- Profile handlers --
  const handleSaveDisplayName = async (e) => {
    e.preventDefault();
    if (!displayName.trim()) { showToast("显示名称不能为空", "error"); return; }
    setIsSavingProfile(true);
    try {
      const res = await api.updateProfile({ display_name: displayName.trim() });
      if (res.data?.user) onUserUpdate(res.data.user);
      showToast("显示名称已更新", "success");
    } catch (e) {
      showToast(e.response?.data?.error || e.response?.data?.detail || "更新失败", "error");
    } finally { setIsSavingProfile(false); }
  };

  // -- Crop helpers --
  const openCropModal = (file) => {
    if (!["image/png","image/jpeg","image/gif","image/webp"].includes(file.type)) {
      showToast("仅支持 PNG、JPEG、GIF、WebP", "error"); return;
    }
    if (file.size > 5 * 1024 * 1024) { showToast("文件不能超过 5MB", "error"); return; }
    const reader = new FileReader();
    reader.onload = (ev) => {
      setCropSrc(ev.target.result);
      setCropScale(1);
      setCropX(0);
      setCropY(0);
      setShowCrop(true);
    };
    reader.readAsDataURL(file);
  };

  const handleCropConfirm = () => {
    const canvas = cropCanvasRef.current;
    if (!canvas) return;
    const outSize = 256;
    const viewSize = 224;
    canvas.width = outSize;
    canvas.height = outSize;
    const ctx = canvas.getContext("2d");
    const img = new Image();
    img.onload = () => {
      const srcLen = Math.min(img.width, img.height);
      const sx0 = (img.width - srcLen) / 2;
      const sy0 = (img.height - srcLen) / 2;
      const sampleLen = srcLen / cropScale;
      const shiftX = (-cropX / viewSize) * sampleLen;
      const shiftY = (-cropY / viewSize) * sampleLen;
      ctx.drawImage(img, sx0 + shiftX, sy0 + shiftY, sampleLen, sampleLen, 0, 0, outSize, outSize);
      canvas.toBlob((blob) => {
        if (blob) {
          setAvatarFile(new File([blob], "avatar.jpg", { type: "image/jpeg" }));
          setAvatarPreview(URL.createObjectURL(blob));
        }
        setShowCrop(false);
        setCropSrc(null);
      }, "image/jpeg", 0.9);
    };
    img.src = cropSrc;
  };

  const handleCropCancel = () => {
    setShowCrop(false);
    setCropSrc(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleCropMouseDown = (e) => {
    setCropDragging(true);
    setCropDragStart({ x: e.clientX - cropX, y: e.clientY - cropY });
  };

  const handleCropMouseMove = (e) => {
    if (!cropDragging) return;
    const maxOffset = 224 * (cropScale - 1);
    const newX = Math.min(0, Math.max(-maxOffset, e.clientX - cropDragStart.x));
    const newY = Math.min(0, Math.max(-maxOffset, e.clientY - cropDragStart.y));
    setCropX(newX);
    setCropY(newY);
  };

  const handleCropMouseUp = () => setCropDragging(false);

  const handleAvatarChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    openCropModal(file);
  };

  const handleUploadAvatar = async () => {
    if (!avatarFile) return;
    setIsUploadingAvatar(true);
    try {
      const fd = new FormData();
      fd.append("file", avatarFile);
      const res = await api.uploadAvatar(fd);
      if (res.data?.user) onUserUpdate(res.data.user);
      setAvatarFile(null);
      showToast("头像已更新", "success");
    } catch (e) {
      showToast(e.response?.data?.error || "上传失败", "error");
    } finally { setIsUploadingAvatar(false); }
  };

  // -- Email handlers --
  const handleSendEmailCode = async () => {
    if (!emailForm.email) {
      showToast("请先输入邮箱", "error");
      return;
    }
    setSendingCode(true);
    try {
      await api.sendAccountEmailCode(emailForm.email);
      setCooldown(60);
      showToast("验证码已发送，请在 10 分钟内完成绑定", "success");
    } catch (e) {
      showToast(e.response?.data?.error || e.response?.data?.detail || "验证码发送失败", "error");
    } finally {
      setSendingCode(false);
    }
  };

  const handleBindEmail = async (event) => {
    event.preventDefault();
    if (!emailForm.email || !emailForm.verification_code) {
      showToast("请填写邮箱和验证码", "error");
      return;
    }
    setSavingEmail(true);
    try {
      const res = await api.bindEmail(emailForm);
      if (res.data?.user) onUserUpdate(res.data.user);
      setEmailForm((value) => ({ ...value, verification_code: "" }));
      showToast("邮箱已绑定", "success");
    } catch (e) {
      showToast(e.response?.data?.error || e.response?.data?.detail || "邮箱绑定失败", "error");
    } finally {
      setSavingEmail(false);
    }
  };

  const handleSendChangePasswordEmailCode = async () => {
    if (!emailEnabled) {
      showToast("邮件服务尚未启用", "error");
      return;
    }
    if (!user?.email) {
      showToast("请先绑定邮箱", "error");
      return;
    }
    setPwdSendingCode(true);
    try {
      await api.sendChangePasswordEmailCode();
      setPwdCooldown(60);
      showToast("验证码已发送，请查收邮箱", "success");
    } catch (e) {
      showToast(e.response?.data?.error || e.response?.data?.detail || "验证码发送失败", "error");
    } finally {
      setPwdSendingCode(false);
    }
  };

  const handleChangePassword = async (event) => {
    event.preventDefault();
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      showToast("两次输入的新密码不一致", "error");
      return;
    }
    if (!/^\d{6}$/.test(passwordForm.verification_code || "")) {
      showToast("请输入 6 位邮箱验证码", "error");
      return;
    }
    setChangingPassword(true);
    try {
      await api.changePassword({
        current_password: passwordForm.current_password,
        new_password: passwordForm.new_password,
        verification_code: passwordForm.verification_code,
      });
      setPasswordForm({ current_password: "", new_password: "", confirm_password: "", verification_code: "" });
      showToast("密码已更新", "success");
    } catch (e) {
      showToast(e.response?.data?.error || e.response?.data?.detail || "密码修改失败", "error");
    } finally {
      setChangingPassword(false);
    }
  };

  const emailEnabled = registerConfig.email_service_enabled || registerConfig.email_verification_required;

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6 relative">
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -20, x: "-50%" }} animate={{ opacity: 1, y: 0, x: "-50%" }} exit={{ opacity: 0, y: -20, x: "-50%" }} className={`fixed top-6 left-1/2 z-[100] px-4 py-3 rounded-2xl flex items-center shadow-2xl border ${toast.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400"}`}>
            <span className="font-medium text-sm">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div>
        <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <User className="text-indigo-500" size={28} />
          用户设置
        </h2>
        <p className="text-slate-500 text-sm mt-1">管理个人资料、邮箱与登录密码</p>
      </div>

      {/* Profile Card */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm space-y-5">
        <h3 className="font-bold text-slate-800 dark:text-slate-100">个人资料</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/60 p-4">
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">账号 ID（学号）</p>
            <p className="mt-1 text-sm font-bold text-slate-800 dark:text-slate-100">{user?.student_id || "-"}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/60 p-4">
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">昵称</p>
            <p className="mt-1 text-sm font-bold text-slate-800 dark:text-slate-100">{user?.display_name || user?.student_id || "-"}</p>
          </div>
        </div>

        <div className="flex items-center gap-5">
          <div className="relative group shrink-0">
            {avatarPreview ? (
              <img src={avatarPreview} alt="" className="w-20 h-20 rounded-full object-cover" />
            ) : (
              <div className="w-20 h-20 rounded-full bg-slate-800 dark:bg-slate-700 flex items-center justify-center text-white text-2xl font-bold">
                {(user?.display_name || user?.student_id || "U")[0].toUpperCase()}
              </div>
            )}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="absolute bottom-0 right-0 w-7 h-7 bg-indigo-500 hover:bg-indigo-600 rounded-full flex items-center justify-center text-white shadow-lg transition-colors"
            >
              <Camera size={14} />
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" onChange={handleAvatarChange} className="hidden" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">头像</p>
            <p className="text-xs text-slate-500">支持 PNG、JPEG、GIF、WebP，最大 5MB</p>
            {avatarFile && (
              <button onClick={handleUploadAvatar} disabled={isUploadingAvatar} className="mt-2 px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50">
                {isUploadingAvatar ? "上传中..." : "保存头像"}
              </button>
            )}
          </div>
        </div>

        {/* Crop Modal */}
        <AnimatePresence>
          {showCrop && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
              onMouseMove={handleCropMouseMove} onMouseUp={handleCropMouseUp} onMouseLeave={handleCropMouseUp}
            >
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
                className="bg-white dark:bg-slate-900 rounded-2xl p-6 shadow-2xl max-w-md w-full space-y-4"
              >
                <h3 className="font-bold text-slate-800 dark:text-slate-100 text-center">裁剪头像</h3>
                <p className="text-xs text-slate-500 text-center">拖拽调整位置 · 滚轮或滑块缩放</p>

                <div
                  className="relative mx-auto rounded-full overflow-hidden cursor-move select-none"
                  style={{ width: 224, height: 224 }}
                  onMouseDown={handleCropMouseDown}
                  onWheel={(e) => {
                    e.preventDefault();
                    const delta = e.deltaY > 0 ? -0.05 : 0.05;
                    setCropScale(s => Math.min(3, Math.max(1, s + delta)));
                  }}
                >
                  {cropSrc && (
                    <img
                      src={cropSrc}
                      alt=""
                      draggable={false}
                      style={{
                        position: "absolute",
                        width: 224 * cropScale,
                        height: 224 * cropScale,
                        objectFit: "cover",
                        left: cropX,
                        top: cropY,
                        pointerEvents: "none",
                      }}
                    />
                  )}
                  <div className="absolute inset-0 rounded-full border-2 border-white/60 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)] pointer-events-none" />
                </div>

                <input
                  type="range" min="1" max="3" step="0.01"
                  value={cropScale}
                  onChange={(e) => setCropScale(parseFloat(e.target.value))}
                  className="w-full accent-indigo-500"
                />

                <div className="flex gap-3 justify-center">
                  <button onClick={handleCropCancel} className="px-5 py-2 bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-xl font-semibold text-sm hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors">取消</button>
                  <button onClick={handleCropConfirm} className="px-5 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl font-semibold text-sm transition-colors">确认裁剪</button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
        <canvas ref={cropCanvasRef} className="hidden" />

        <form onSubmit={handleSaveDisplayName} className="space-y-1.5">
          <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">显示名称</label>
          <div className="flex gap-2">
            <input
              type="text" maxLength={64}
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder={user?.student_id || "输入显示名称"}
              className="flex-1 px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100"
            />
            <button type="submit" disabled={isSavingProfile} className="shrink-0 px-5 py-3 bg-slate-800 hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 text-white text-sm font-semibold rounded-xl transition-colors disabled:opacity-50">
              {isSavingProfile ? "保存中..." : "保存"}
            </button>
          </div>
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <form onSubmit={handleBindEmail} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                <Mail size={20} className="text-indigo-500" /> 绑定邮箱
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                {user?.email ? `${user.email} · ${user.email_verified ? "已验证" : "未验证"}` : "当前未绑定邮箱"}
              </p>
            </div>
            {user?.email_verified ? (
              <span className="px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs font-bold">VERIFIED</span>
            ) : (
              <span className="px-2.5 py-1 rounded-full bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs font-bold">PENDING</span>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">邮箱地址</label>
            <div className="flex gap-2">
              <input
                type="email"
                disabled={!emailEnabled}
                value={emailForm.email}
                onChange={(e) => setEmailForm({ ...emailForm, email: e.target.value })}
                placeholder="you@example.com"
                className="flex-1 min-w-0 px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100 disabled:opacity-60"
              />
              <button
                type="button"
                onClick={handleSendEmailCode}
                disabled={!emailEnabled || sendingCode || cooldown > 0}
                className="shrink-0 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-400 text-white text-sm font-bold rounded-xl transition-colors"
              >
                {sendingCode ? "发送中" : cooldown > 0 ? `${cooldown}s` : "验证码"}
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">邮箱验证码</label>
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              disabled={!emailEnabled}
              value={emailForm.verification_code}
              onChange={(e) => setEmailForm({ ...emailForm, verification_code: e.target.value.replace(/\D/g, "").slice(0, 6) })}
              placeholder="123456"
              className="w-full px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm tracking-[0.3em] focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100 disabled:opacity-60"
            />
          </div>

          {!emailEnabled && (
            <div className="rounded-2xl border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
              邮件服务尚未启用。配置 SMTP 后，这里会自动开放绑定和换绑。
            </div>
          )}

          <button type="submit" disabled={!emailEnabled || savingEmail} className="w-full py-3.5 bg-slate-800 hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 text-white font-bold rounded-xl transition-colors disabled:opacity-50">
            {savingEmail ? "保存中..." : user?.email ? "更新邮箱" : "绑定邮箱"}
          </button>
        </form>

        <form onSubmit={handleChangePassword} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm space-y-5">
          <div>
            <h3 className="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
              <Lock size={20} className="text-indigo-500" /> 修改密码
            </h3>
            <p className="text-xs text-slate-500 mt-1">修改后下次登录使用新密码，当前会话保持有效。</p>
          </div>

          {[
            ["current_password", "当前密码"],
            ["new_password", "新密码"],
            ["confirm_password", "再次输入新密码"],
          ].map(([key, label]) => (
            <div className="space-y-1.5" key={key}>
              <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">{label}</label>
              <input
                type="password"
                value={passwordForm[key]}
                onChange={(e) => setPasswordForm({ ...passwordForm, [key]: e.target.value })}
                placeholder="••••••••"
                className="w-full px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100"
              />
            </div>
          ))}

          <div className="space-y-1.5">
            <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">邮箱验证码</label>
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                disabled={!emailEnabled || !user?.email}
                value={passwordForm.verification_code}
                onChange={(e) => setPasswordForm({ ...passwordForm, verification_code: e.target.value.replace(/\D/g, "").slice(0, 6) })}
                placeholder="123456"
                className="flex-1 min-w-0 px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm tracking-[0.3em] focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100 disabled:opacity-60"
              />
              <button
                type="button"
                onClick={handleSendChangePasswordEmailCode}
                disabled={!emailEnabled || !user?.email || pwdSendingCode || pwdCooldown > 0}
                className="shrink-0 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-400 text-white text-sm font-bold rounded-xl transition-colors"
              >
                {pwdSendingCode ? "发送中" : pwdCooldown > 0 ? `${pwdCooldown}s` : "验证码"}
              </button>
            </div>
            {!user?.email && (
              <p className="text-xs text-slate-500">请先绑定邮箱后再修改密码</p>
            )}
          </div>

          <button type="submit" disabled={changingPassword} className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl transition-colors disabled:opacity-50">
            {changingPassword ? "更新中..." : "更新密码"}
          </button>
        </form>
      </div>
    </motion.div>
  );
}
function KeysManager() {
  const [keys, setKeys] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [toast, setToast] = useState(null);
  
  // Create Key Modal
  const [showConfig, setShowConfig] = useState(false);
  const [newKeyData, setNewKeyData] = useState({ name: '', group_name: 'claude', expires_at: '', quota_limit: '' });
  const [isCreating, setIsCreating] = useState(false);
  
  // Show Key Success Modal
    const [createdKey, setCreatedKey] = useState(null);
  const [customExpiry, setCustomExpiry] = useState(false);

  const setExpiryPreset = (days) => {
    if (!days) {
      setNewKeyData({...newKeyData, expires_at: ''});
      setCustomExpiry(false);
      return;
    }
    if (days === 'custom') {
      setCustomExpiry(true);
      return;
    }
    const d = new Date();
    d.setDate(d.getDate() + days);
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    setNewKeyData({...newKeyData, expires_at: d.toISOString().slice(0, 16)});
    setCustomExpiry(false);
  };


  const showToast = (msg, type) => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 2500);
  };

  const fetchKeys = () => {
    setIsLoading(true);
    api.getKeys().then(res => setKeys(res.data.keys || [])).catch(() => showToast("加载失败", "error")).finally(() => setIsLoading(false));
  };
  useEffect(() => { fetchKeys(); }, []);

  useEffect(() => {
    if (showConfig || createdKey) {
      document.body.style.paddingRight = `${window.innerWidth - document.documentElement.clientWidth}px`;
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    };
  }, [showConfig, createdKey]);

  useEffect(() => {
    if (showConfig || createdKey) {
      document.body.style.paddingRight = `${window.innerWidth - document.documentElement.clientWidth}px`;
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.paddingRight = '0px';
      document.body.style.overflow = 'unset';
    };
  }, [showConfig, createdKey]);

  const handleCreateNew = async () => {
    if (!newKeyData.name) {
      showToast("请填写秘钥名称", "error");
      return;
    }
    setIsCreating(true);
    try {
      const res = await api.createKeyEx(newKeyData);
      if (res.data.ok) {
        showToast("创建成功", "success");
        setCreatedKey(res.data.key);
        setShowConfig(false);
        setNewKeyData({ name: '', group_name: 'claude', expires_at: '', quota_limit: '' });
        fetchKeys();
      } else {
        showToast(res.data.error || "创建失败", "error");
      }
    } catch(e) {
      showToast("网络错误", "error");
    }
    setIsCreating(false);
  };

  const deleteKey = async (id) => {
    if(!window.confirm("确定永久删除它吗？")) return;
    try {
      await api.deleteKey(id);
      showToast("已删除", "success");
      fetchKeys();
    } catch(e) { showToast("删除失败", "error"); }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6 relative">
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -20, x: "-50%" }} animate={{ opacity: 1, y: 0, x: "-50%" }} exit={{ opacity: 0, y: -20, x: "-50%" }} className={`fixed top-6 left-1/2 z-[100] px-4 py-3 rounded-2xl flex items-center shadow-2xl border ${ toast.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400" }`}>
            <span className="font-medium text-sm">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Key className="text-indigo-500" size={28} />
            访问密钥 (API Keys)
          </h2>
          <p className="text-slate-500 text-sm mt-1">管理用于请求大模型的认证密钥</p>
        </div>
        <button onClick={() => setShowConfig(true)} className="flex items-center gap-2 px-5 py-2.5 bg-indigo-500 hover:bg-indigo-600 text-white font-medium rounded-xl shadow-lg shadow-indigo-500/20 transition-all active:scale-95">
          <Plus size={18} />
          生成新密钥
        </button>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/50 dark:bg-slate-950/50 border-b border-slate-100 dark:border-slate-800">
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">名称</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">秘钥前缀</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">分组</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">限额</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">使用情况</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {isLoading ? (
                <tr><td colSpan="6" className="p-8 text-center"><Activity className="animate-spin text-indigo-500 mx-auto" /></td></tr>
              ) : keys.length === 0 ? (
                <tr><td colSpan="6" className="p-8 text-center text-slate-400">目前没有秘钥，点击右上角生成</td></tr>
              ) : keys.map(k => (
                <tr key={k.id} className="group hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                  <td className="px-6 py-4 font-medium text-slate-700 dark:text-slate-200">{k.name}</td>
                  <td className="px-6 py-4">
                    <code className="text-xs font-mono bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-300 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800">
                      {k.key_prefix}...
                    </code>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500">{keyGroupLabel(k.group_name)}</td>
                  <td className="px-6 py-4 text-sm text-slate-500">{!k.quota_limit || Number(k.quota_limit) === 0 ? '无限制' : formatUsd(k.quota_limit)}</td>
                  <td className="px-6 py-4 text-sm font-mono text-slate-500">{formatUsd(k.used_usd || 0)}</td>
                  <td className="px-6 py-4 text-right">
                    <button onClick={() => deleteKey(k.id)} className="p-2 text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-xl transition-colors">
                      <Trash2 size={18} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Config Create Modal */}
      <AnimatePresence>
        {showConfig && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm sm:p-6">
            <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl w-full max-w-md overflow-hidden flex flex-col shadow-2xl">
              <div className="px-6 py-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <h3 className="font-bold flex items-center gap-2 text-slate-800 dark:text-slate-100">
                  <Target size={20} className="text-indigo-500" /> 高级秘钥配置
                </h3>
                <button onClick={() => setShowConfig(false)} className="p-2 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-full text-slate-400">
                  <X size={20} />
                </button>
              </div>
              <div className="p-6 space-y-5">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1">名称标识</label>
                  <input type="text" value={newKeyData.name} onChange={e => setNewKeyData({...newKeyData, name: e.target.value})} placeholder="例如：开发环境密钥" className="w-full px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100"/>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-2">模型分组</label>
                  <div className="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800/50 rounded-xl">
                    {['claude', 'kimi', 'mimo', 'gpt'].map(g => (
                      <button
                        key={g}
                        onClick={() => setNewKeyData({...newKeyData, group_name: g})}
                        className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${newKeyData.group_name === g ? 'bg-white dark:bg-slate-700 shadow-sm text-indigo-600 dark:text-indigo-400' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'}`}
                      >
                        {keyGroupLabel(g)}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-2 flex items-center justify-between">
                    过期时间
                    {!customExpiry && newKeyData.expires_at && <span className="text-indigo-500 font-mono text-[10px]">{new Date(newKeyData.expires_at).toLocaleDateString()} 到期</span>}
                  </label>
                  <div className="grid grid-cols-4 gap-2 mb-2">
                    {[
                      { label: '7天', val: 7 },
                      { label: '1个月', val: 30 },
                      { label: '永久', val: null },
                      { label: '自定义', val: 'custom' },
                    ].map(p => {
                      const isActive = (p.val === null && !newKeyData.expires_at && !customExpiry) || (p.val === 'custom' && customExpiry);
                      return (
                        <button
                          key={p.label}
                          onClick={() => setExpiryPreset(p.val)}
                          className={`py-2 text-xs font-bold rounded-xl border transition-all ${isActive ? 'bg-indigo-50 border-indigo-200 text-indigo-600 dark:bg-indigo-500/20 dark:border-indigo-500/30 dark:text-indigo-400' : 'bg-slate-50 border-slate-200 text-slate-500 hover:bg-slate-100 dark:bg-[#0B1120] dark:border-slate-800 dark:hover:bg-slate-800/50'}`}
                        >
                          {p.label}
                        </button>
                      );
                    })}
                  </div>
                  {customExpiry && (
                    <motion.input initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} type="datetime-local" value={newKeyData.expires_at} onChange={e => setNewKeyData({...newKeyData, expires_at: e.target.value})} className="w-full px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100 mt-2"/>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1">请求限额 (USD / 0为无限制)</label>
                  <input type="number" min="0" step="0.01" value={newKeyData.quota_limit} onChange={e => setNewKeyData({...newKeyData, quota_limit: e.target.value})} placeholder="0.00" className="w-full px-4 py-3 bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/50 outline-none text-slate-800 dark:text-slate-100"/>
                </div>
                <button onClick={handleCreateNew} disabled={isCreating} className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl shadow-lg transition-all active:scale-95 disabled:opacity-50">
                  {isCreating ? '生成中...' : '确认生成'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Secret Key Display Modal */}
      <AnimatePresence>
        {createdKey && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm sm:p-6">
            <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl w-full max-w-sm overflow-hidden flex flex-col shadow-2xl">
              <div className="p-8 text-center space-y-6">
                <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-500 rounded-full flex items-center justify-center mx-auto mb-2">
                  <CheckCircle2 size={32} />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100">密钥创建成功</h3>
                  <p className="text-sm text-slate-500 mt-2">请务必保存。为了安全起见，此密钥以后将不会再次显示。</p>
                </div>
                <div className="bg-slate-50 dark:bg-[#0B1120] border border-slate-200 dark:border-slate-800 p-4 rounded-xl relative group">
                  <code className="text-indigo-600 dark:text-indigo-400 font-mono text-sm break-all select-all block mb-2">{createdKey}</code>
                  <button onClick={() => { navigator.clipboard.writeText(createdKey); showToast("已复制完整的秘钥！", "success"); }} className="w-full py-2.5 mt-2 flex items-center justify-center gap-2 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 font-medium rounded-lg transition-colors">
                    <Copy size={16} /> 点击并复制
                  </button>
                </div>
                <button onClick={() => setCreatedKey(null)} className="w-full py-3.5 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl shadow-lg transition-all active:scale-95">
                  我已妥善保存
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </motion.div>
  );
}

function LogsView() {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  useEffect(() => { 
    api.getLogs()
      .then(res => {
        setLogs(res.data.logs || res.data || []);
        setCurrentPage(1);
      })
      .catch(console.error)
      .finally(() => setIsLoading(false)); 
  }, []);

  const uniqueModels = Array.from(new Set(logs.map(l => l.model || 'Unknown')));
  const colors = ["#8b5cf6", "#10b981", "#f59e0b", "#3b82f6", "#ef4444", "#ec4899", "#06b6d4", "#84cc16"];
  const chartData = [...logs].reverse().map(log => {
    const d = new Date(log.timestamp);
    const point = {
      time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    uniqueModels.forEach(m => point[m] = 0);
    const modelName = log.model || 'Unknown';
    point[modelName] = log.total_tokens || 0;
    return point;
  });
  const totalPages = Math.max(1, Math.ceil(logs.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const pagedLogs = logs.slice((safePage - 1) * pageSize, safePage * pageSize);

  useEffect(() => {
    if (currentPage !== safePage) {
      setCurrentPage(safePage);
    }
  }, [currentPage, safePage]);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-8">
      <header>
        <h1 className="text-3xl font-extrabold tracking-tight mb-2 text-slate-800 dark:text-slate-100">调用日志</h1>
        <p className="text-slate-500 dark:text-slate-400">查看您近期的 API 请求以及消耗趋势。</p>
      </header>

      {/* Chart Section */}
      {!isLoading && logs.length > 0 && (
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border border-slate-200 dark:border-slate-800 rounded-3xl p-6 shadow-sm">
          <h3 className="font-bold text-slate-700 dark:text-slate-200 mb-6 flex items-center gap-2">
            <Activity className="text-indigo-500" size={20} /> 模型调用趋势
          </h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    {uniqueModels.map((model, idx) => (
                      <linearGradient key={`grad-${model}`} id={`color-${idx}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={colors[idx % colors.length]} stopOpacity={0.3}/>
                        <stop offset="95%" stopColor={colors[idx % colors.length]} stopOpacity={0}/>
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" strokeOpacity={0.2} />
                  <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} dx={-10} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderRadius: '12px', border: 'none', color: '#fff', fontSize: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                    itemStyle={{ fontSize: '12px', fontWeight: 'bold' }}
                  />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                  {uniqueModels.map((model, idx) => (
                    <Area 
                      key={model} 
                      type="monotone" 
                      name={model} 
                      dataKey={model} 
                      stroke={colors[idx % colors.length]} 
                      strokeWidth={3} 
                      fillOpacity={1} 
                      fill={`url(#color-${idx})`} 
                      connectNulls={true}
                    />
                  ))}
                </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      )}

      {/* Logs Table Section */}
      <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border border-slate-200 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left whitespace-nowrap">
            <thead className="bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md/50 border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">时间</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">模型</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">消耗成本明细</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider text-right">总 Tokens</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
              {isLoading ? (
                <tr><td colSpan="4" className="p-8 text-center text-slate-400"><Activity className="animate-spin mx-auto text-indigo-500" /></td></tr>
              ) : logs.length === 0 ? (
                <tr><td colSpan="4" className="p-12 text-center text-slate-500 italic">暂无日志。</td></tr>
              ) : pagedLogs.map((log, idx) => (
                <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                  <td className="px-6 py-4 text-sm font-mono text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col">
                      <span>{new Date(log.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
                      <span className="text-xs opacity-70">{new Date(log.timestamp).toLocaleTimeString()}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    <span className="bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 px-2 py-1 rounded-md border border-indigo-100 dark:border-indigo-500/20">{log.model || "未知"}</span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="space-y-1.5 text-xs font-mono">
                      {log.input_tokens > 0 && (
                        <div className="text-slate-500">
                          In {log.input_tokens.toLocaleString()} x {formatPricePer1M(log.input_price_per_1m)} = <span className="text-slate-700 dark:text-slate-300">{formatUsd(log.input_cost_usd)}</span>
                        </div>
                      )}
                      {log.output_tokens > 0 && (
                        <div className="text-slate-500">
                          Out {log.output_tokens.toLocaleString()} x {formatPricePer1M(log.output_price_per_1m)} = <span className="text-slate-700 dark:text-slate-300">{formatUsd(log.output_cost_usd)}</span>
                        </div>
                      )}
                      {log.cache_read_tokens > 0 && (
                        <div className="text-emerald-600 dark:text-emerald-300">
                          Cache Read {log.cache_read_tokens.toLocaleString()} x {formatPricePer1M(log.cache_read_price_per_1m)} = {formatUsd(log.cache_read_cost_usd)}
                        </div>
                      )}
                      {log.cache_creation_tokens > 0 && (
                        <div className="text-amber-600 dark:text-amber-300">
                          Cache Write {log.cache_creation_tokens.toLocaleString()} x {formatPricePer1M(log.cache_write_price_per_1m)} = {formatUsd(log.cache_write_cost_usd)}
                        </div>
                      )}
                      <div className="pt-1 text-indigo-600 dark:text-indigo-300 font-semibold">
                        Total USD: {formatUsd(log.cost_usd || 0)}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className={`px-3 py-1 rounded-full text-xs font-bold ${log.total_tokens > 5000 ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}>
                      {log.total_tokens?.toLocaleString()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!isLoading && logs.length > 0 && (
          <div className="flex flex-col gap-3 border-t border-slate-200 px-6 py-4 text-sm dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-slate-500 dark:text-slate-400">
              第 {safePage} / {totalPages} 页
              <span className="ml-2">
                显示 {(safePage - 1) * pageSize + 1}-{Math.min(safePage * pageSize, logs.length)} / {logs.length}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                disabled={safePage === 1}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <ChevronLeft size={16} />
                上一页
              </button>
              <button
                onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                disabled={safePage === totalPages}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                下一页
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
