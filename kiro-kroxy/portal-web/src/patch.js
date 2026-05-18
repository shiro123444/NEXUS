import fs from 'fs';
let code = fs.readFileSync('portal-web/src/App.jsx', 'utf8');

// 1. Fix map errors
code = code.replace(/res => setKeys\(res\.data\)/g, 'res => setKeys(res.data.keys || res.data || [])');
code = code.replace(/res => setLogs\(res\.data\)/g, 'res => setLogs(res.data.logs || res.data || [])');
code = code.replace(/stats\.map/g, '(stats || []).map');
code = code.replace(/keys\.map/g, '(keys || []).map');
code = code.replace(/logs\.map/g, '(logs || []).map');

// 2. Add Background Fetch and remove Purple Background
// We will replace the Background UI
code = code.replace(/<div className="absolute top-\[-10%\] left-\[-10%\] w-\[40vw\] h-\[40vh\].*?\/>/g, '');
code = code.replace(/<div className="absolute bottom-\[-10%\] right-\[-10%\] w-\[40vw\] h-\[40vh\].*?\/>/g, '');
code = code.replace(/bg-gradient-to-r from-indigo-600 to-purple-600/g, 'bg-slate-900 dark:bg-slate-900 border border-slate-200 dark:border-slate-800');
code = code.replace(/bg-gradient-to-r from-purple-500 to-indigo-600/g, 'bg-slate-800');

// Add bg hook
code = code.replace('api = {', `api = {\n  getBg: () => axios.get("/api/bg/active"),`);

// Update App to use Background
const appBodyOld = `
export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isDark, setIsDark] = useDarkMode();
`;
const appBodyNew = `
export default function App() {
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
    backgroundImage: \`url(\${bgInfo.url})\`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundAttachment: 'fixed'
  } : {};
`;
code = code.replace(appBodyOld, appBodyNew);

// Add the background overlay
code = code.replace(/className={\`min-h-screen transition-colors duration-300 font-sans (.*?)\`}/, 'className={`min-h-screen transition-colors duration-300 font-sans relative $1`} style={bgStyle}');
code = code.replace(/<AnimatePresence mode="wait">/g, 
`{bgInfo.url && <div className="absolute inset-0 z-0 bg-slate-50 dark:bg-slate-950" style={{ opacity: 1 - bgInfo.opacity }}></div>}
      <div className="relative z-10 min-h-screen flex flex-col pt-0">
        <AnimatePresence mode="wait">`);
code = code.replace(/<\/AnimatePresence>\n    <\/div>/g, 
`</AnimatePresence>\n      </div>\n    </div>`);

code = code.replace(/bg-slate-50 dark:bg-slate-950/g, 'bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md');
code = code.replace(/bg-white dark:bg-slate-900/g, 'bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg');

fs.writeFileSync('portal-web/src/App.jsx', code);
