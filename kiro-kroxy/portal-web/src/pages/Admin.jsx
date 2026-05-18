import React, { useState, useEffect } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { Users, Activity, FileText, LogOut, ChevronRight, ShieldAlert, BarChart3, Database, Key, Power, AlertCircle, Plus, Minus, Trash2, Settings, Calendar } from "lucide-react";
import logoImg from "../assets/logo.png";

const api = {
  checkAuth: () => axios.get("/api/admin/auth/me"),
  login: (data) => axios.post("/api/admin/auth/login", data),
  logout: () => axios.post("/api/admin/auth/logout"),
  getStats: () => axios.get("/api/admin/full-stats"),
  getUsers: () => axios.get("/api/admin/users"),
  updateUserStatus: (id, isActive) => axios.put(`/api/admin/users/${id}`, {is_active: isActive}),
  updateUserQuota: (id, amount) => axios.post(`/api/admin/users/${id}/quota`, {amount}),
  getKeys: () => axios.get("/api/admin/keys"),
  toggleKey: (id, isActive) => axios.post(`/api/admin/keys/${id}/toggle`, {is_active: isActive}),
  deleteKey: (id) => axios.delete(`/api/admin/keys/${id}`),
  getLogs: () => axios.get("/api/admin/all-logs?limit=100"),
  getCheckinConfig: () => axios.get("/api/admin/checkin/config"),
  updateCheckinConfig: (data) => axios.post("/api/admin/checkin/config", data),
  batchUpdateQuota: (amount, userIds=[]) => axios.post("/api/admin/users/quota/batch", { amount, user_ids: userIds }),
};

function formatUsd(value) {
  const amount = Number(value || 0);
  return `$${amount.toFixed(amount >= 1 ? 4 : 6)}`;
}

export default function Admin() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [activeTab, setActiveTab] = useState("overview");

  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [keys, setKeys] = useState([]);
  const [logs, setLogs] = useState([]);
  const [checkinConfig, setCheckinConfig] = useState({ min_usd: 0, max_usd: 0 });
  const [toast, setToast] = useState(null);
  const [confirmModal, setConfirmModal] = useState({ open: false, msg: "", onConfirm: null });
  const [selectedUserIds, setSelectedUserIds] = useState([]);
  const [batchAmount, setBatchAmount] = useState(10);

  const showToast = (msg, type='success') => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const showConfirm = (msg, onConfirm) => {
    setConfirmModal({ open: true, msg, onConfirm });
  };

  // Modals
  const [quotaModal, setQuotaModal] = useState({ open: false, user: null, amount: 0, isAdd: true });
  const [detailsModal, setDetailsModal] = useState({ open: false, user: null });

  useEffect(() => {
    checkAdmin();
  }, []);

  useEffect(() => {
    if (isAdmin) {
      if (activeTab === "overview") loadStats();
      if (activeTab === "users") loadUsers();
      if (activeTab === "keys") loadKeys();
      if (activeTab === "logs") loadLogs();
      if (activeTab === "settings") loadConfig();
    }
  }, [isAdmin, activeTab]);

  const checkAdmin = async () => {
    try {
      await api.checkAuth();
      setIsAdmin(true);
    } catch {
      setIsAdmin(false);
    }
    setLoading(false);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      await api.login({ username, password });
      setIsAdmin(true);
    } catch (e) {
      showToast("登录失败，请检查账密", "error");
    }
  };

  const handleLogout = async () => {
    await api.logout();
    setIsAdmin(false);
  };

  const loadStats = async () => {
    try {
      const res = await api.getStats();
      setStats(res.data);
    } catch (e) { console.error(e); }
  };

  const loadUsers = async () => {
    try {
      const res = await api.getUsers();
      setUsers(res.data.users || []);
    } catch (e) { console.error(e); }
  };

  const loadKeys = async () => {
    try {
      const res = await api.getKeys();
      setKeys(res.data.keys || []);
    } catch (e) { console.error(e); }
  };

  const loadLogs = async () => {
    try {
      const res = await api.getLogs();
      setLogs(res.data.logs || []);
    } catch (e) { console.error(e); }
  };

  const loadConfig = async () => {
    try {
      const res = await api.getCheckinConfig();
      setCheckinConfig(res.data);
    } catch (e) { console.error(e); }
  };

  const handleSaveConfig = async () => {
    try {
      await api.updateCheckinConfig(checkinConfig);
      showToast("配置保存成功", "success");
    } catch (e) { showToast("保存超时或失败", "error"); }
  };

  const handleToggleUser = async (user) => {
    try {
      await api.updateUserStatus(user.id, !user.is_active);
      loadUsers();
    } catch (e) { console.error(e); }
  };

  const toggleSelectUser = (userId) => {
    setSelectedUserIds((prev) => prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]);
  };

  const toggleSelectAllUsers = () => {
    const activeIds = users.filter((u) => u.is_active).map((u) => u.id);
    if (activeIds.length === selectedUserIds.length) {
      setSelectedUserIds([]);
    } else {
      setSelectedUserIds(activeIds);
    }
  };

  const handleBatchQuota = async () => {
    if (selectedUserIds.length === 0) {
      showToast("请先选择用户", "error");
      return;
    }
    try {
      await api.batchUpdateQuota(batchAmount, selectedUserIds);
      loadUsers();
      setSelectedUserIds([]);
      showToast("批量增加余额成功", "success");
    } catch (e) {
      showToast("批量增加余额失败", "error");
    }
  };

  const handleQuotaSubmit = async () => {
    try {
      let finalAmount = quotaModal.amount;
      if (!quotaModal.isAdd) finalAmount = -finalAmount;
      await api.updateUserQuota(quotaModal.user.id, finalAmount);
      setQuotaModal({ ...quotaModal, open: false });
      loadUsers();
      showToast("操作成功", "success");
      showToast("操作成功", "success");
    } catch (e) { showToast("更新额度失败", "error"); }
  };

  const handleToggleKey = async (keyInfo) => {
    try {
      await api.toggleKey(keyInfo.id, !keyInfo.is_active);
      loadKeys();
    } catch (e) { console.error(e); }
  };

  const handleDeleteKey = async (id) => {
    showConfirm("确定永久删除该秘钥吗？此操作不可逆。", async () => {
      try {
        await api.deleteKey(id);
        loadKeys();
        showToast("已成功删除秘钥", "success");
      } catch (e) { showToast("删除秘钥失败", "error"); }
    });
  };

  if (loading) return null;

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm bg-neutral-900 border border-neutral-800 rounded-2xl p-8">
          <div className="flex flex-col items-center mb-8">
            <img src={logoImg} alt="Logo" className="h-16 mb-4" />
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <ShieldAlert className="text-indigo-400" /> 管理员入口
            </h1>
          </div>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <input type="text" placeholder="管理员账号" value={username} onChange={e => setUsername(e.target.value)} className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500" required />
            </div>
            <div>
              <input type="password" placeholder="密码" value={password} onChange={e => setPassword(e.target.value)} className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500" required />
            </div>
            <button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 rounded-xl transition-colors">
              验证登录
            </button>
          </form>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-white flex">
      {/* Sidebar */}
      <div className="w-64 border-r border-neutral-900 flex flex-col">
        <div className="p-6 flex items-center gap-3">
          <img src={logoImg} alt="Nexus Portal" className="h-8" />
          <span className="font-bold tracking-wider">Nexus 后台</span>
        </div>
        <nav className="flex-1 px-4 space-y-2">
          {[
            { id: "overview", icon: Activity, label: "运行大盘" },
            { id: "users", icon: Users, label: "用户管理" },
            { id: "keys", icon: Key, label: "秘钥管理" },
            { id: "logs", icon: FileText, label: "请求日志" },
            { id: "settings", icon: Settings, label: "系统设置" }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-xl text-sm transition-all ${activeTab === tab.id ? 'bg-indigo-500/10 text-indigo-400 font-medium' : 'text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200'}`}
            >
              <div className="flex items-center gap-3">
                <tab.icon size={18} />
                {tab.label}
              </div>
              {activeTab === tab.id && <ChevronRight size={16} />}
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-neutral-900">
          <button onClick={handleLogout} className="w-full flex items-center gap-3 px-4 py-3 text-sm text-neutral-400 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-all">
            <LogOut size={18} />
            安全退出
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 p-8 overflow-y-auto relative">
        <AnimatePresence mode="wait">
          {activeTab === 'overview' && (
            <motion.div key="overview" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6">
              <h2 className="text-2xl font-bold">监控中心</h2>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {[
                  { label: "活跃用户数", value: stats?.active_users || 0, icon: Users, color: "text-blue-400" },
                  { label: "存活秘钥数", value: stats?.active_keys || 0, icon: Key, color: "text-emerald-400" },
                  { label: "用户总余额", value: formatUsd(stats?.total_balance_usd), icon: Database, color: "text-purple-400" },
                  { label: "今日请求笔数", value: (stats?.today_requests || 0).toLocaleString(), icon: BarChart3, color: "text-rose-400" }
                ].map((stat, i) => (
                  <div key={i} className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6 flex flex-col justify-between">
                    <div className="flex items-center gap-3 text-neutral-400 mb-4">
                      <stat.icon size={20} className={stat.color} />
                      <span className="text-sm font-medium">{stat.label}</span>
                    </div>
                    <span className="text-3xl font-semibold tracking-tight">{stat.value}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {activeTab === 'users' && (
            <motion.div key="users" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6">
              <h2 className="text-2xl font-bold">用户目录</h2>
              <div className="flex flex-col gap-4 rounded-2xl border border-neutral-800 bg-neutral-900 p-5 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <button onClick={toggleSelectAllUsers} className="rounded-xl border border-neutral-700 px-4 py-2 text-sm text-neutral-200 transition-colors hover:bg-neutral-800">
                    {users.filter((u) => u.is_active).length === selectedUserIds.length && selectedUserIds.length > 0 ? "取消全选" : "全选活跃用户"}
                  </button>
                  <span className="text-sm text-neutral-400">已选 {selectedUserIds.length} 人</span>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <input
                    type="number"
                    step="0.01"
                    value={batchAmount}
                    onChange={(e) => setBatchAmount(parseFloat(e.target.value) || 0)}
                    className="w-full rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 sm:w-40"
                  />
                  <button onClick={handleBatchQuota} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700">
                    一键增加额度
                  </button>
                </div>
              </div>
              <div className="bg-neutral-900 border border-neutral-800 rounded-2xl overflow-hidden">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-neutral-950/50 text-neutral-400 border-b border-neutral-800">
                    <tr>
                      <th className="px-6 py-4 font-medium">选择</th>
                      <th className="px-6 py-4 font-medium">账号/学号</th>
                      <th className="px-6 py-4 font-medium">邮箱</th>
                      <th className="px-6 py-4 font-medium">累计消费</th>
                      <th className="px-6 py-4 font-medium">当前余额</th>
                      <th className="px-6 py-4 font-medium">状态</th>
                      <th className="px-6 py-4 font-medium text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800/50">
                    {users.map(u => (
                      <tr key={u.id} className="hover:bg-neutral-800/20 transition-colors">
                        <td className="px-6 py-4">
                          <input type="checkbox" checked={selectedUserIds.includes(u.id)} onChange={() => toggleSelectUser(u.id)} className="h-4 w-4 rounded border-neutral-700 bg-neutral-950 text-indigo-500 focus:ring-indigo-500" />
                        </td>
                        <td className="px-6 py-4 text-neutral-200 font-medium">
                          {u.username || u.student_id}
                          {u.notes && <div className="text-xs text-neutral-500 font-normal mt-1">{u.notes}</div>}
                        </td>
                        <td className="px-6 py-4 text-neutral-400">
                          {u.email ? (
                            <div>
                              <div className="font-mono text-xs">{u.email}</div>
                              <div className={`mt-1 text-[10px] font-bold ${u.email_verified ? 'text-emerald-400' : 'text-amber-400'}`}>
                                {u.email_verified ? '已验证' : '未验证'}
                              </div>
                            </div>
                          ) : (
                            <span className="text-neutral-600">未绑定</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-neutral-400 font-mono">{formatUsd(u.total_cost_usd || 0)}</td>
                        <td className="px-6 py-4 text-indigo-300 font-mono">{formatUsd(u.balance_usd || 0)}</td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${u.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                            {u.is_active ? '正常' : '封禁'}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center justify-end gap-2">
                            <button onClick={() => setDetailsModal({ open: true, user: u })} className="p-2 text-neutral-400 hover:text-indigo-400 hover:bg-neutral-800 rounded-lg transition-colors" title="详情">
                              <FileText size={16} />
                            </button>
                            <button onClick={() => setQuotaModal({ open: true, user: u, amount: 10, isAdd: true })} className="p-2 text-neutral-400 hover:text-emerald-400 hover:bg-neutral-800 rounded-lg transition-colors" title="调整额度">
                              <Database size={16} />
                            </button>
                            <button onClick={() => handleToggleUser(u)} className={`p-2 rounded-lg transition-colors ${u.is_active ? 'text-neutral-400 hover:text-orange-400 hover:bg-neutral-800' : 'text-rose-400 hover:bg-neutral-800'}`} title={u.is_active ? "停用" : "启用"}>
                              <Power size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {activeTab === 'keys' && (
            <motion.div key="keys" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6">
              <h2 className="text-2xl font-bold">API 秘钥池</h2>
              <div className="bg-neutral-900 border border-neutral-800 rounded-2xl overflow-hidden">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-neutral-950/50 text-neutral-400 border-b border-neutral-800">
                    <tr>
                      <th className="px-6 py-4 font-medium">归属用户 (ID)</th>
                      <th className="px-6 py-4 font-medium">前缀</th>
                      <th className="px-6 py-4 font-medium">使用 / 限额</th>
                      <th className="px-6 py-4 font-medium">状态</th>
                      <th className="px-6 py-4 font-medium text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800/50">
                    {keys.map((k, i) => (
                      <tr key={i} className="hover:bg-neutral-800/20 transition-colors">
                        <td className="px-6 py-4 text-neutral-200">User #{k.user_id}</td>
                        <td className="px-6 py-4 font-mono text-neutral-400">{k.key_prefix}...</td>
                        <td className="px-6 py-4 text-xs text-neutral-500">{formatUsd(k.used_usd || 0)} / {!k.quota_limit || Number(k.quota_limit) === 0 ? '无限制' : formatUsd(k.quota_limit)}</td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${k.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-orange-500/10 text-orange-400'}`}>
                            {k.is_active ? '启用' : '禁用'}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center justify-end gap-2">
                            <button onClick={() => handleToggleKey(k)} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors">
                              <Power size={16} />
                            </button>
                            <button onClick={() => handleDeleteKey(k.id)} className="p-2 text-neutral-400 hover:text-red-400 hover:bg-neutral-800 rounded-lg transition-colors">
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {activeTab === 'logs' && (
            <motion.div key="logs" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6">
              <h2 className="text-2xl font-bold">审计日志</h2>
              <div className="bg-neutral-900 border border-neutral-800 rounded-2xl overflow-hidden">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-neutral-950/50 text-neutral-400 border-b border-neutral-800">
                    <tr>
                      <th className="px-6 py-4 font-medium">请求时间</th>
                      <th className="px-6 py-4 font-medium">账号</th>
                      <th className="px-6 py-4 font-medium">底层路由</th>
                      <th className="px-6 py-4 font-medium">状态</th>
                      <th className="px-6 py-4 font-medium">延迟</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800/50">
                    {logs.map((L, i) => (
                      <tr key={i} className="hover:bg-neutral-800/20 transition-colors text-neutral-400">
                        <td className="px-6 py-3">{new Date(L.created_at * 1000).toLocaleString()}</td>
                        <td className="px-6 py-3 font-medium text-neutral-300">{L.student_id || '-'}</td>
                        <td className="px-6 py-3 font-mono text-xs text-indigo-300/80">{L.model || L.path || '-'}</td>
                        <td className="px-6 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${L.status_code === 200 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                            HTTP {L.status_code}
                          </span>
                        </td>
                        <td className="px-6 py-3 text-xs">{L.duration ? (L.duration*1000).toFixed(0)+'ms' : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {activeTab === 'settings' && (
            <motion.div key="settings" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6">
              <h2 className="text-2xl font-bold">系统设置</h2>
              <div className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6 w-full max-w-2xl">
                <div className="flex items-center gap-3 mb-6 pb-4 border-b border-neutral-800">
                  <div className="p-3 bg-indigo-500/10 text-indigo-400 rounded-xl">
                    <Calendar size={24} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold">每日签到奖励配置</h3>
                    <p className="text-sm text-neutral-400 mt-1">设置用户每日签到可获得的美元余额区间。</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div>
                    <label className="block text-sm text-neutral-400 mb-2">最小奖励 (USD)</label>
                    <input type="number" 
                           step="0.0001"
                           value={checkinConfig.min_usd || 0} 
                           onChange={e => setCheckinConfig({...checkinConfig, min_usd: parseFloat(e.target.value) || 0})}
                           className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors" />
                  </div>
                  <div>
                    <label className="block text-sm text-neutral-400 mb-2">最大奖励 (USD)</label>
                    <input type="number" 
                           step="0.0001"
                           value={checkinConfig.max_usd || 0} 
                           onChange={e => setCheckinConfig({...checkinConfig, max_usd: parseFloat(e.target.value) || 0})}
                           className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors" />
                  </div>
                </div>
                <button onClick={handleSaveConfig} className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2.5 rounded-xl text-sm font-medium transition-colors">
                  持久化保存
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Quota Modal */}
      <AnimatePresence>
        {quotaModal.open && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }} className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-sm overflow-hidden">
                <div className="p-6">
                <h3 className="text-lg font-bold mb-4">余额调整 - {quotaModal.user?.username || quotaModal.user?.student_id}</h3>
                <div className="flex gap-2 mb-4 bg-neutral-950 p-1 rounded-xl">
                  <button onClick={() => setQuotaModal({...quotaModal, isAdd: true})} className={`flex-1 py-2 text-sm font-medium rounded-lg flex justify-center items-center gap-2 ${quotaModal.isAdd ? 'bg-indigo-600 text-white' : 'text-neutral-400 hover:text-white'}`}>
                    <Plus size={16} /> 增加
                  </button>
                  <button onClick={() => setQuotaModal({...quotaModal, isAdd: false})} className={`flex-1 py-2 text-sm font-medium rounded-lg flex justify-center items-center gap-2 ${!quotaModal.isAdd ? 'bg-rose-600 text-white' : 'text-neutral-400 hover:text-white'}`}>
                    <Minus size={16} /> 扣除
                  </button>
                </div>
                <input type="number" 
                       value={quotaModal.amount} 
                       step="0.01"
                       onChange={e => setQuotaModal({...quotaModal, amount: parseFloat(e.target.value) || 0})} 
                       className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500 mb-6" />
                <div className="flex gap-3">
                  <button onClick={() => setQuotaModal({...quotaModal, open: false})} className="flex-1 py-3 bg-neutral-800 hover:bg-neutral-700 rounded-xl text-sm font-medium transition-colors">取消</button>
                  <button onClick={handleQuotaSubmit} className={`flex-1 py-3 rounded-xl text-sm font-medium transition-colors ${quotaModal.isAdd ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-rose-600 hover:bg-rose-700'}`}>确认执行</button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Detail Modal */}
      <AnimatePresence>
        {detailsModal.open && (
           <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
           <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }} className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-md overflow-hidden">
             <div className="p-6">
               <h3 className="text-xl font-bold mb-2">详单: {detailsModal.user?.username || detailsModal.user?.student_id}</h3>
               <div className="text-sm text-neutral-400 mb-6 font-mono space-y-2">
                 <p>User ID: {detailsModal.user?.id}</p>
                 <p>当前余额: {formatUsd(detailsModal.user?.balance_usd || 0)}</p>
                 <p>累计消费: {formatUsd(detailsModal.user?.total_cost_usd || 0)}</p>
                 <p>注册时间: {detailsModal.user?.created_at ? new Date(detailsModal.user.created_at * 1000).toLocaleString() : '-'}</p>
                 <p>备注信息: {detailsModal.user?.notes || '无'}</p>
               </div>
               <button onClick={() => setDetailsModal({ open: false, user: null })} className="w-full py-3 bg-neutral-800 hover:bg-neutral-700 rounded-xl text-sm font-medium transition-colors">关闭面板</button>
             </div>
           </motion.div>
         </motion.div>
        )}
      </AnimatePresence>


      <AnimatePresence>
        {confirmModal.open && (
           <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
           <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }} className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-sm overflow-hidden">
             <div className="p-6">
               <h3 className="text-lg font-bold mb-4 flex items-center gap-2 text-rose-400">
                 <AlertCircle size={20}/> 警告
               </h3>
               <p className="text-neutral-300 text-sm mb-6">{confirmModal.msg}</p>
               <div className="flex gap-3">
                 <button onClick={() => setConfirmModal({ open: false })} className="flex-1 py-3 bg-neutral-800 hover:bg-neutral-700 rounded-xl text-sm font-medium transition-colors">取消</button>
                 <button onClick={() => { confirmModal.onConfirm(); setConfirmModal({ open: false }); }} className="flex-1 py-3 bg-rose-600 hover:bg-rose-700 rounded-xl text-sm text-white font-medium transition-colors">确认执行</button>
               </div>
             </div>
           </motion.div>
         </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -20, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: -20, x: "-50%" }}
            className={`fixed top-6 left-1/2 z-[100] px-4 py-3 rounded-2xl flex items-center shadow-2xl border ${
              toast.type === "success" 
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
                : "bg-rose-500/10 border-rose-500/20 text-rose-400"
            }`}
          >
            {toast.type === "success" ? <ShieldAlert size={20} className="mr-2" /> : <AlertCircle size={20} className="mr-2" />}
            <span className="font-medium text-sm">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>


      <AnimatePresence>
        {confirmModal.open && (
           <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
           <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }} className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-sm overflow-hidden">
             <div className="p-6">
               <h3 className="text-lg font-bold mb-4 flex items-center gap-2 text-rose-400">
                 <AlertCircle size={20}/> 警告
               </h3>
               <p className="text-neutral-300 text-sm mb-6">{confirmModal.msg}</p>
               <div className="flex gap-3">
                 <button onClick={() => setConfirmModal({ open: false })} className="flex-1 py-3 bg-neutral-800 hover:bg-neutral-700 rounded-xl text-sm font-medium transition-colors">取消</button>
                 <button onClick={() => { confirmModal.onConfirm(); setConfirmModal({ open: false }); }} className="flex-1 py-3 bg-rose-600 hover:bg-rose-700 rounded-xl text-sm text-white font-medium transition-colors">确认执行</button>
               </div>
             </div>
           </motion.div>
         </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -20, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: -20, x: "-50%" }}
            className={`fixed top-6 left-1/2 z-[100] px-4 py-3 rounded-2xl flex items-center shadow-2xl border ${
              toast.type === "success" 
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
                : "bg-rose-500/10 border-rose-500/20 text-rose-400"
            }`}
          >
            {toast.type === "success" ? <ShieldAlert size={20} className="mr-2" /> : <AlertCircle size={20} className="mr-2" />}
            <span className="font-medium text-sm">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}
