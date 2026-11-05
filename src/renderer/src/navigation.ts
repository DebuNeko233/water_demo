/** The starter has four simple views; no router dependency is needed yet. */
export const navigationItems = [
  {
    id: 'overview',
    label: '应用概览',
    icon: '◈',
    description: '可独立调试、离线分发的桌面应用起点。',
  },
  {
    id: 'http',
    label: 'HTTP 示例',
    icon: '◇',
    description: '通过 Electron 主进程调用 FastAPI，查看 Python 的响应。',
  },
  {
    id: 'tasks',
    label: '实时任务',
    icon: '◎',
    description: '启动或取消 Python 任务，并通过 WebSocket 查看实时事件。',
  },
  {
    id: 'ipc',
    label: 'IPC 示例',
    icon: '▣',
    description: '通过受限的 Preload API 调用文件选择等桌面功能。',
  },
] as const

export type PageId = (typeof navigationItems)[number]['id']
