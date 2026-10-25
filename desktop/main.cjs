'use strict'

const { app, BrowserWindow, Menu, dialog, session, shell } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { randomBytes } = require('node:crypto')
const { BackendProcess } = require('./lib/backend.cjs')
const { TOKEN_HEADER, isBackendUrl, isExportUrl, isAllowedExternalUrl, authenticatedHeaders } = require('./lib/policy.cjs')
const { sanitizePreferences } = require('./lib/preferences.cjs')
const { rendererSmoke, waitForSmokePaint } = require('./lib/smoke.cjs')

const smokeTest = process.argv.includes('--smoke-test')
const root = path.resolve(__dirname, '..')
const brandingDirectory = app.isPackaged ? path.join(process.resourcesPath, 'branding') : path.join(__dirname, 'resources')
app.setName(app.isPackaged ? 'Vocabulary Notebook' : 'Vocabulary Notebook Dev')
let userData = process.env.VOCAB_DESKTOP_USER_DATA_DIR
if (userData && !path.isAbsolute(userData)) throw new Error('VOCAB_DESKTOP_USER_DATA_DIR 必须是绝对路径')
if (!userData && smokeTest) userData = fs.mkdtempSync(path.join(os.tmpdir(), 'vocab-desktop-smoke-'))
userData ||= path.join(app.getPath('appData'), app.getName())
fs.mkdirSync(userData, { recursive: true, mode: 0o700 })
app.setPath('userData', userData)
const dataDirectory = path.join(userData, 'data')
const preferencesFile = path.join(userData, 'desktop-preferences.json')
const token = randomBytes(32).toString('hex')
let backend
let origin
let mainWindow
let desktopSession
let quitting = false
let finalExit = false
let exitCode = 0
let failing = false

function readPreferences() {
  try { return sanitizePreferences(JSON.parse(fs.readFileSync(preferencesFile, 'utf8'))) }
  catch { return {} }
}

async function savePreferences() {
  if (!mainWindow || mainWindow.isDestroyed() || !isBackendUrl(mainWindow.webContents.getURL(), origin)) return
  try {
    const snapshot = await Promise.race([
      mainWindow.webContents.executeJavaScript(`({theme: localStorage.getItem('theme'), 'vocabulary-word-sort': localStorage.getItem('vocabulary-word-sort')})`),
      new Promise(resolve => setTimeout(() => resolve(null), 1000)),
    ])
    if (snapshot === null) return
    const temporary = `${preferencesFile}.tmp`
    fs.writeFileSync(temporary, `${JSON.stringify(sanitizePreferences(snapshot))}\n`, { mode: 0o600 })
    fs.renameSync(temporary, preferencesFile)
  } catch { /* 偏好写入失败不阻止本地服务正常退出。 */ }
}

async function fail(message) {
  if (failing || quitting) return
  failing = true
  exitCode = 1
  if (smokeTest) console.error(`DESKTOP_SMOKE_FAILED ${message}`)
  else await dialog.showMessageBox({ type: 'error', title: '词汇笔记本', message, detail: `数据目录：${dataDirectory}\n词库不会因此删除。`, buttons: ['退出'] })
  app.quit()
}

function openExternal(url) {
  if (isAllowedExternalUrl(url)) shell.openExternal(url).catch(() => {
    if (!smokeTest) dialog.showErrorBox('无法打开浏览器', '请检查系统默认浏览器后重试。')
  })
}

function download(url) {
  if (mainWindow && isExportUrl(url, origin)) {
    mainWindow.webContents.downloadURL(url, { headers: { [TOKEN_HEADER]: token } })
  }
}

function installSession() {
  desktopSession = session.fromPartition('persist:vocabulary-notebook')
  desktopSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
  desktopSession.setPermissionCheckHandler(() => false)
  desktopSession.webRequest.onBeforeSendHeaders((details, callback) => {
    callback({ requestHeaders: authenticatedHeaders(details.url, details.requestHeaders, origin, token) })
  })
  desktopSession.webRequest.onHeadersReceived((details, callback) => {
    if (!isBackendUrl(details.url, origin)) { callback({}); return }
    callback({ responseHeaders: { ...details.responseHeaders, 'Content-Security-Policy': [
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-src 'none'; frame-ancestors 'none'; form-action 'self'",
    ] } })
  })
  if (smokeTest) {
    desktopSession.webRequest.onBeforeRequest((details, callback) => {
      const url = new URL(details.url)
      // 冒烟验收只访问隔离的本机服务，不连接已有 Ollama 或远端字体。
      callback({ cancel: !isBackendUrl(details.url, origin) || url.pathname === '/api/health' })
    })
  }
  desktopSession.on('will-download', (event, item) => {
    if (!isExportUrl(item.getURL(), origin)) { event.preventDefault(); return }
    if (smokeTest) {
      const downloadDirectory = path.join(userData, 'smoke-downloads')
      fs.mkdirSync(downloadDirectory, { recursive: true })
      item.setSavePath(path.join(downloadDirectory, path.basename(item.getFilename())))
    } else item.setSaveDialogOptions({ title: '导出词汇笔记本', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())) })
    item.once('done', (_event, state) => {
      if (state === 'interrupted' && !smokeTest) dialog.showErrorBox('导出未完成', '请检查保存位置后重试。')
    })
  })
}

function installMenu() {
  const menu = []
  if (process.platform === 'darwin') menu.push({ label: '词汇笔记本', submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' }, { type: 'separator' }, { role: 'quit' }] })
  menu.push({ label: '文件', submenu: [
    { label: '打开数据目录', click: () => shell.openPath(dataDirectory) },
    { type: 'separator' },
    { role: process.platform === 'darwin' ? 'close' : 'quit' },
  ] })
  menu.push({ label: '编辑', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] })
  menu.push({ label: '显示', submenu: [{ role: 'reload' }, { type: 'separator' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { type: 'separator' }, { role: 'togglefullscreen' }] })
  menu.push({ label: '窗口', submenu: [{ role: 'minimize' }, { role: 'zoom' }] })
  Menu.setApplicationMenu(Menu.buildFromTemplate(menu))
}

async function createWindow() {
  const window = new BrowserWindow({
    width: 1180, height: 820, minWidth: 480, minHeight: 600,
    title: '词汇笔记本', backgroundColor: '#171715', show: false,
    icon: path.join(brandingDirectory, process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
    webPreferences: {
      session: desktopSession, nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, webviewTag: false, allowRunningInsecureContent: false,
      backgroundThrottling: !smokeTest,
      preload: path.join(__dirname, 'lib', 'preferences-preload.cjs'),
      additionalArguments: [`--vocab-origin=${origin}`, `--vocab-preferences=${JSON.stringify(readPreferences())}`, `--vocab-window=${randomBytes(8).toString('hex')}`],
    },
  })
  mainWindow = window
  window.once('ready-to-show', () => { if (!smokeTest && !quitting) window.show() })
  window.on('close', event => { if (!finalExit) { event.preventDefault(); app.quit() } })
  window.on('closed', () => { mainWindow = null })
  window.webContents.on('will-attach-webview', event => event.preventDefault())
  window.webContents.on('will-navigate', (event, url) => {
    if (isExportUrl(url, origin)) { event.preventDefault(); download(url) }
    else if (!isBackendUrl(url, origin)) { event.preventDefault(); openExternal(url) }
  })
  window.webContents.on('will-redirect', (event, url) => { if (!isBackendUrl(url, origin)) event.preventDefault() })
  window.webContents.on('will-frame-navigate', event => {
    if (!event.isMainFrame && !isBackendUrl(event.url, origin)) event.preventDefault()
  })
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (isExportUrl(url, origin)) download(url)
    else if (isBackendUrl(url, origin)) window.loadURL(url).catch(() => fail('页面加载失败，请重启应用。'))
    else openExternal(url)
    return { action: 'deny' }
  })
  window.webContents.on('render-process-gone', () => { if (!quitting) fail('界面意外退出，请重启应用。') })
  window.webContents.on('did-fail-load', (_event, code, _description, _url, isMainFrame) => {
    if (isMainFrame && code !== -3 && !quitting) fail('页面加载失败，请重启应用。')
  })
  await window.loadURL(origin)
  return window
}

async function runSmokeTest(window) {
  const result = await window.webContents.executeJavaScript(`(${rendererSmoke.toString()})()`)
  const unauthenticated = await fetch(`${origin}/api/desktop/health`)
  if (![401, 403].includes(unauthenticated.status)) throw new Error('桌面服务未拒绝无令牌请求')
  result.unauthenticatedBlocked = true
  const downloaded = new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('原生导出下载超时')), 15000)
    desktopSession.once('will-download', (_event, item) => {
      item.once('done', (_downloadEvent, state) => {
        clearTimeout(timer)
        if (state !== 'completed') { reject(new Error('原生导出下载未完成')); return }
        try {
          const exported = JSON.parse(fs.readFileSync(item.getSavePath(), 'utf8'))
          if (exported.words.length !== 1 || exported.words[0].word !== 'Desktop-smoke') throw new Error('原生导出内容不符合预期')
          resolve(true)
        } catch (error) { reject(error) }
      })
    })
  })
  await window.webContents.executeJavaScript("void window.open('/api/words/export?format=json', '_blank')")
  result.nativeDownload = await downloaded
  await window.loadURL(origin)
  if (process.env.VOCAB_DESKTOP_SMOKE_SCREENSHOT) window.showInactive()
  result.painted = await window.webContents.executeJavaScript(`(${waitForSmokePaint.toString()})()`)
  if (process.env.VOCAB_DESKTOP_SMOKE_SCREENSHOT) {
    const screenshotPath = process.env.VOCAB_DESKTOP_SMOKE_SCREENSHOT
    if (!path.isAbsolute(screenshotPath)) throw new Error('冒烟截图必须使用绝对路径')
    fs.writeFileSync(screenshotPath, (await window.webContents.capturePage()).toPNG())
  }
  console.log(`DESKTOP_SMOKE_OK ${JSON.stringify(result)}`)
  app.quit()
}

async function start() {
  if (process.platform === 'darwin' && !app.isPackaged) app.dock.setIcon(path.join(brandingDirectory, 'icon.png'))
  if (process.platform === 'win32') app.setAppUserModelId('net.ericzhou.vocabulary-notebook')
  fs.mkdirSync(dataDirectory, { recursive: true, mode: 0o700 })
  if (smokeTest) {
    if (fs.readdirSync(dataDirectory).length) throw new Error('冒烟验收需要空数据目录，以免读取已有词库或凭据。')
    fs.writeFileSync(path.join(dataDirectory, 'config.json'), JSON.stringify({
      provider: 'ollama', ollama: { url: 'http://127.0.0.1:9/api/generate', model: 'qwen2.5:7b' },
      deepseek: { api_key: '', model: 'deepseek-chat' },
    }), { flag: 'wx', mode: 0o600 })
  }
  const pythonSuffix = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
  const projectPython = path.join(root, '.venv', pythonSuffix)
  const command = app.isPackaged
    ? path.join(process.resourcesPath, 'backend', process.platform === 'win32' ? 'vocab-backend.exe' : 'vocab-backend')
    : process.env.VOCAB_DESKTOP_PYTHON || (fs.existsSync(projectPython) ? projectPython : path.join(root, '.venv-desktop', pythonSuffix))
  const args = app.isPackaged ? [] : ['-u', path.join(root, 'desktop_backend.py')]
  const environment = { ...process.env, VOCAB_DESKTOP_DATA_DIR: dataDirectory, VOCAB_DESKTOP_TOKEN: token, PYTHONUNBUFFERED: '1' }
  delete environment.VOCAB_DATA_FILE
  delete environment.VOCAB_DESKTOP_ORIGIN
  backend = new BackendProcess(command, args, { cwd: dataDirectory, env: environment })
  backend.on('unexpected-exit', () => fail('本地服务意外停止，请重启应用。'))
  origin = await backend.start()
  if (quitting) return
  installSession()
  installMenu()
  const window = await createWindow()
  if (smokeTest && !quitting) await runSmokeTest(window)
}

if (!app.requestSingleInstanceLock()) app.quit()
else {
  app.on('second-instance', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
  app.on('activate', () => {
    if (mainWindow) mainWindow.show()
    else if (origin && !quitting) createWindow().catch(() => fail('页面加载失败，请重启应用。'))
  })
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', event => {
    if (finalExit) return
    event.preventDefault()
    if (quitting) return
    quitting = true
    ;(async () => {
      await savePreferences()
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.destroy()
      await backend?.stop()
      finalExit = true
      app.exit(exitCode)
    })().catch(() => app.exit(1))
  })
  process.on('SIGINT', () => app.quit())
  process.on('SIGTERM', () => app.quit())
  app.whenReady().then(start).catch(error => fail(error.message))
}
