import dayjs, { type ConfigType, type Dayjs } from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

/** 产品默认展示时区: 中国标准时间 UTC+8 */
export const APP_TIMEZONE = 'Asia/Shanghai'

const HAS_TZ = /([zZ]|[+-]\d{2}:?\d{2})$/

/**
 * 解析接口时间。
 * - 带 Z / ±00:00 等: 按该时区解析
 * - 无时区的 naive 字符串: 按 UTC 解释(后端多用 utcnow / timestamptz 存 UTC)
 * 最终可转到 Asia/Shanghai 展示。
 */
export function parseApiTime(value: ConfigType): Dayjs {
  if (value == null || value === '') return dayjs(NaN)
  if (typeof value === 'string') {
    const s = value.trim()
    if (!s) return dayjs(NaN)
    if (HAS_TZ.test(s)) return dayjs(s)
    // "2026-07-28T06:20:15.382179" → 当作 UTC
    return dayjs.utc(s)
  }
  return dayjs(value)
}

/** 转为东八区 dayjs */
export function toAppTime(value: ConfigType): Dayjs {
  return parseApiTime(value).tz(APP_TIMEZONE)
}

export function formatDateTime(
  value: ConfigType,
  pattern = 'YYYY-MM-DD HH:mm:ss',
): string {
  const d = toAppTime(value)
  return d.isValid() ? d.format(pattern) : '-'
}

export function formatDate(value: ConfigType, pattern = 'YYYY-MM-DD'): string {
  return formatDateTime(value, pattern)
}

export function formatTime(value: ConfigType, pattern = 'HH:mm:ss'): string {
  return formatDateTime(value, pattern)
}

export function formatFromNow(value: ConfigType): string {
  const d = toAppTime(value)
  return d.isValid() ? d.fromNow() : '-'
}

export function diffFromNow(
  value: ConfigType,
  unit: dayjs.QUnitType | dayjs.OpUnitType = 'day',
): number {
  const d = toAppTime(value)
  if (!d.isValid()) return 0
  return d.diff(dayjs().tz(APP_TIMEZONE), unit)
}
