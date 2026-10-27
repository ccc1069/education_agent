import '@ant-design/v5-patch-for-react-19'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, App as AntdApp, Empty } from 'antd'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
import 'dayjs/locale/zh-cn'

import App from './App'
import { antdTheme } from './lib/antd/theme'
import { antdZhCN } from './lib/antd/locale'
import { APP_TIMEZONE } from './lib/datetime'
import { queryClient } from './lib/query/queryClient'
import { useAuthStore } from './lib/store/authStore'
import './styles/global.css'

dayjs.extend(relativeTime)
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.locale('zh-cn')
dayjs.tz.setDefault(APP_TIMEZONE)

// 初始化时从 localStorage 恢复登录状态
useAuthStore.getState().init()

async function enableMock() {
  if (import.meta.env.VITE_USE_MOCK !== 'true') return
  const { worker } = await import('./mocks/browser')
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
    quiet: false,
  })
  console.info(
    '%c[MSW] Mock 模式已启用',
    'color:#1B4332;font-weight:bold;font-size:13px;',
    '\n演示账号: student@demo.com / teacher@demo.com / admin@demo.com',
    '\n统一密码: demo123456',
  )
}

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('#root not found')

enableMock().finally(() => {
  createRoot(rootEl).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider
          theme={antdTheme}
          locale={antdZhCN}
          renderEmpty={() => (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
          )}
        >
          <AntdApp>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AntdApp>
        </ConfigProvider>
      </QueryClientProvider>
    </StrictMode>,
  )
})
