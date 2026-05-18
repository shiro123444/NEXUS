import { createHmac, timingSafeEqual } from 'node:crypto'
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs'
import { extname, join, normalize } from 'node:path'
import http from 'node:http'
import { pipeline } from 'node:stream'
import { URL } from 'node:url'

const PORT = Number(process.env.PORT || 8094)
const AUTH_PASSWORD = process.env.AUTH_PASSWORD || ''
const SESSION_SECRET = process.env.SESSION_SECRET || ''
const STATIC_DIR = process.env.STATIC_DIR || '/var/www/metacubexd'
const UPSTREAM = new URL(process.env.UPSTREAM_URL || 'http://127.0.0.1:19090')
const MIHOMO_SECRET = process.env.MIHOMO_SECRET || ''
const COOKIE_NAME = 'clash_session'
const SESSION_MAX_AGE = 60 * 60 * 24 * 30

if (!AUTH_PASSWORD || !SESSION_SECRET || !MIHOMO_SECRET) {
  throw new Error('Missing AUTH_PASSWORD, SESSION_SECRET, or MIHOMO_SECRET')
}

const loginHtml = readFileSync(join(STATIC_DIR, 'login.html'), 'utf8')

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.json': 'application/json; charset=utf-8',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
}

function signSession(expiresAt) {
  return createHmac('sha256', SESSION_SECRET)
    .update(`${expiresAt}:${AUTH_PASSWORD}`)
    .digest('hex')
}

function buildSessionCookie() {
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_MAX_AGE
  const token = `${expiresAt}.${signSession(expiresAt)}`
  return `${COOKIE_NAME}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_MAX_AGE}`
}

function clearSessionCookie() {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`
}

function parseCookies(req) {
  const cookieHeader = req.headers.cookie || ''
  return Object.fromEntries(
    cookieHeader
      .split(';')
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        const idx = item.indexOf('=')
        if (idx === -1) return [item, '']
        return [item.slice(0, idx), decodeURIComponent(item.slice(idx + 1))]
      }),
  )
}

function isAuthed(req) {
  const cookies = parseCookies(req)
  const raw = cookies[COOKIE_NAME]
  if (!raw) return false

  const [expiresAtStr, signature] = raw.split('.')
  if (!expiresAtStr || !signature) return false

  const expiresAt = Number(expiresAtStr)
  if (!Number.isFinite(expiresAt) || expiresAt < Math.floor(Date.now() / 1000)) {
    return false
  }

  const expected = signSession(expiresAt)
  const actualBuf = Buffer.from(signature)
  const expectedBuf = Buffer.from(expected)
  if (actualBuf.length !== expectedBuf.length) return false

  return timingSafeEqual(actualBuf, expectedBuf)
}

function send(res, statusCode, body, contentType = 'text/plain; charset=utf-8', headers = {}) {
  res.writeHead(statusCode, { 'Content-Type': contentType, ...headers })
  res.end(body)
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', (chunk) => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
    req.on('error', reject)
  })
}

function serveFile(res, filePath) {
  const ext = extname(filePath).toLowerCase()
  const contentType = MIME_TYPES[ext] || 'application/octet-stream'
  const stat = statSync(filePath)

  res.writeHead(200, {
    'Content-Type': contentType,
    'Content-Length': stat.size,
    'Cache-Control': ext === '.html' ? 'no-store' : 'public, max-age=31536000, immutable',
  })

  pipeline(createReadStream(filePath), res, () => {})
}

function resolveStaticPath(pathname) {
  const cleanedPath = normalize(decodeURIComponent(pathname)).replace(/^\/+/, '')
  const resolved = join(STATIC_DIR, cleanedPath)
  if (!resolved.startsWith(STATIC_DIR)) return null
  return resolved
}

function proxyHttp(req, res) {
  const upstreamPath = req.url.replace(/^\/api/, '') || '/'
  const options = {
    protocol: UPSTREAM.protocol,
    hostname: UPSTREAM.hostname,
    port: UPSTREAM.port,
    method: req.method,
    path: upstreamPath,
    headers: {
      ...req.headers,
      host: `${UPSTREAM.hostname}:${UPSTREAM.port}`,
      authorization: `Bearer ${MIHOMO_SECRET}`,
      connection: req.headers.upgrade ? 'upgrade' : 'keep-alive',
    },
  }

  delete options.headers.cookie

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode || 502, proxyRes.headers)
    pipeline(proxyRes, res, () => {})
  })

  proxyReq.on('error', (error) => {
    send(res, 502, JSON.stringify({ error: 'upstream_error', detail: error.message }), 'application/json; charset=utf-8')
  })

  pipeline(req, proxyReq, () => {})
}

function proxyUpgrade(req, socket, head) {
  if (!isAuthed(req)) {
    socket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n')
    socket.destroy()
    return
  }

  const upstreamSocket = http.request({
    protocol: UPSTREAM.protocol,
    hostname: UPSTREAM.hostname,
    port: UPSTREAM.port,
    method: 'GET',
    path: req.url.replace(/^\/api/, '') || '/',
    headers: {
      ...req.headers,
      host: `${UPSTREAM.hostname}:${UPSTREAM.port}`,
      authorization: `Bearer ${MIHOMO_SECRET}`,
      connection: 'upgrade',
      upgrade: req.headers.upgrade || 'websocket',
    },
  })

  upstreamSocket.on('upgrade', (proxyRes, proxySocket, proxyHead) => {
    socket.write(
      `HTTP/1.1 ${proxyRes.statusCode} ${proxyRes.statusMessage}\r\n` +
        Object.entries(proxyRes.headers)
          .map(([key, value]) => `${key}: ${value}`)
          .join('\r\n') +
        '\r\n\r\n',
    )
    if (head?.length) proxySocket.write(head)
    if (proxyHead?.length) socket.write(proxyHead)
    proxySocket.pipe(socket)
    socket.pipe(proxySocket)
  })

  upstreamSocket.on('error', () => socket.destroy())
  upstreamSocket.end()
}

async function handleLogin(req, res) {
  const rawBody = await readBody(req)
  let payload

  try {
    payload = JSON.parse(rawBody || '{}')
  } catch {
    send(res, 400, JSON.stringify({ ok: false, message: 'Invalid JSON' }), 'application/json; charset=utf-8')
    return
  }

  if ((payload.password || '') !== AUTH_PASSWORD) {
    send(res, 401, JSON.stringify({ ok: false, message: 'Wrong password' }), 'application/json; charset=utf-8')
    return
  }

  send(
    res,
    200,
    JSON.stringify({ ok: true }),
    'application/json; charset=utf-8',
    { 'Set-Cookie': buildSessionCookie() },
  )
}

const server = http.createServer(async (req, res) => {
  const { pathname } = new URL(req.url, `http://${req.headers.host || 'localhost'}`)

  if (pathname === '/health') {
    send(res, 200, 'ok')
    return
  }

  if (pathname === '/login' && req.method === 'GET') {
    if (isAuthed(req)) {
      res.writeHead(302, { Location: '/' })
      res.end()
      return
    }
    send(res, 200, loginHtml, 'text/html; charset=utf-8', { 'Cache-Control': 'no-store' })
    return
  }

  if (pathname === '/login' && req.method === 'POST') {
    await handleLogin(req, res)
    return
  }

  if (pathname === '/logout') {
    res.writeHead(302, { Location: '/login', 'Set-Cookie': clearSessionCookie() })
    res.end()
    return
  }

  if (!isAuthed(req)) {
    if (pathname.startsWith('/api/')) {
      send(res, 401, JSON.stringify({ error: 'unauthorized' }), 'application/json; charset=utf-8')
      return
    }
    res.writeHead(302, { Location: '/login' })
    res.end()
    return
  }

  if (pathname === '/api') {
    res.writeHead(301, { Location: '/api/' })
    res.end()
    return
  }

  if (pathname.startsWith('/api/')) {
    proxyHttp(req, res)
    return
  }

  const staticPath = resolveStaticPath(pathname === '/' ? '/index.html' : pathname)
  const fallbackPath = join(STATIC_DIR, 'index.html')

  if (staticPath && existsSync(staticPath) && statSync(staticPath).isFile()) {
    serveFile(res, staticPath)
    return
  }

  serveFile(res, fallbackPath)
})

server.on('upgrade', (req, socket, head) => {
  if (!req.url.startsWith('/api/')) {
    socket.destroy()
    return
  }
  proxyUpgrade(req, socket, head)
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`metacubexd gateway listening on 127.0.0.1:${PORT}`)
})
