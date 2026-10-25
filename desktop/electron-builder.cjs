const fs = require('node:fs');
const path = require('node:path');

module.exports = {
  appId: 'net.ericzhou.vocabulary-notebook',
  productName: 'Vocabulary Notebook',
  electronDist: path.join(__dirname, 'node_modules/electron/dist'),
  directories: { output: 'release', buildResources: 'resources' },
  // 显式白名单：不把仓库、开发环境、词库或凭据装入应用。
  files: ['main.cjs', 'lib/**/*.cjs', 'package.json'],
  extraResources: [
    { from: 'build/backend/vocab-backend', to: 'backend', filter: ['**/*'] },
    { from: '../LICENSE', to: 'LICENSE.vocabulary-notebook.txt' },
    { from: 'resources', to: 'branding', filter: ['icon.png', 'icon.ico'] },
  ],
  asar: true,
  npmRebuild: false,
  publish: null,
  artifactName: '${productName}-${version}-${os}-${arch}.${ext}',
  mac: {
    icon: 'icon.icns',
    category: 'public.app-category.education',
    target: ['dmg', 'zip'],
    identity: '-',
    hardenedRuntime: false,
    notarize: false,
  },
  win: { icon: 'icon.ico', target: ['nsis'], requestedExecutionLevel: 'asInvoker' },
  dmg: {
    background: 'background.png',
    icon: 'icon.icns',
    iconSize: 80,
    iconTextSize: 12,
    contents: [
      { x: 150, y: 200 },
      { x: 390, y: 200, type: 'link', path: '/Applications' },
    ],
  },
  nsis: {
    oneClick: false,
    perMachine: false,
    allowToChangeInstallationDirectory: true,
    deleteAppDataOnUninstall: false,
    createDesktopShortcut: true,
    installerIcon: 'icon.ico',
    uninstallerIcon: 'icon.ico',
    installerHeader: 'installerHeader.bmp',
    installerSidebar: 'installerSidebar.bmp',
    uninstallerSidebar: 'installerSidebar.bmp',
  },
  beforePack: async (context) => {
    const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, 'build/backend/target.json'), 'utf8'));
    const arch = { 1: 'x64', 3: 'arm64' }[context.arch];
    if (manifest.platform !== context.electronPlatformName || manifest.arch !== arch) {
      throw new Error('内置 Python 后端与 Electron 平台/架构不匹配；请在目标平台重新构建。');
    }
  },
};
