import zhCN from 'antd/locale/zh_CN'
import type { Locale } from 'antd/es/locale'

/** 补全周/月简称,避免日历弹层回落到英文 */
const SHORT_WEEK_DAYS = ['日', '一', '二', '三', '四', '五', '六']
const SHORT_MONTHS = [
  '1月',
  '2月',
  '3月',
  '4月',
  '5月',
  '6月',
  '7月',
  '8月',
  '9月',
  '10月',
  '11月',
  '12月',
]

const datePickerLang = {
  ...(zhCN.DatePicker?.lang ?? {}),
  // rc-picker 会 locale.split('_'),缺此字段会直接崩溃
  locale: zhCN.DatePicker?.lang?.locale ?? 'zh_CN',
  shortWeekDays: SHORT_WEEK_DAYS,
  shortMonths: SHORT_MONTHS,
}

export const antdZhCN = {
  ...zhCN,
  DatePicker: {
    ...zhCN.DatePicker,
    lang: datePickerLang,
    timePickerLocale: {
      placeholder: '请选择时间',
      ...(zhCN.DatePicker?.timePickerLocale ?? {}),
    },
  },
  Empty: {
    description: '暂无数据',
  },
  Table: {
    ...(zhCN.Table ?? {}),
    emptyText: '暂无数据',
  },
} as Locale
