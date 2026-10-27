import { useState } from 'react'
import { App, Button, Upload } from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { InboxOutlined, DeleteOutlined } from '@ant-design/icons'
import type { RcFile } from 'antd/es/upload'

const MAX_SIZE_MB = 4
const SUPPORTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']

interface ImageUploaderProps {
  maxCount?: number
  value?: string[]
  onChange?: (dataUrls: string[]) => void
}

export function ImageUploader({ maxCount = 4, value = [], onChange }: ImageUploaderProps) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<UploadFile[]>([])

  const beforeUpload = (file: RcFile): false | typeof Upload.LIST_IGNORE => {
    if (!SUPPORTED_TYPES.includes(file.type)) {
      message.error(`不支持的图片格式: ${file.type},仅支持 PNG/JPEG/WebP/GIF`)
      return Upload.LIST_IGNORE
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      message.error(`图片 ${file.name} 超过 ${MAX_SIZE_MB}MB 限制`)
      return Upload.LIST_IGNORE
    }
    if (files.length >= maxCount) {
      message.error(`最多 ${maxCount} 张图片`)
      return Upload.LIST_IGNORE
    }
    const reader = new FileReader()
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string
      const newFile: UploadFile = {
        uid: `rc-${Date.now()}-${Math.random()}`,
        name: file.name,
        status: 'done',
        url: dataUrl,
        size: file.size,
        type: file.type,
      }
      const next = [...files, newFile]
      setFiles(next)
      onChange?.(next.map((f) => f.url!).filter(Boolean))
    }
    reader.readAsDataURL(file)
    return false
  }

  const handleRemove = (uid: string) => {
    const next = files.filter((f) => f.uid !== uid)
    setFiles(next)
    onChange?.(next.map((f) => f.url!).filter(Boolean))
  }

  return (
    <div>
      <Upload.Dragger
        multiple
        listType="picture-card"
        fileList={files}
        beforeUpload={beforeUpload}
        accept={SUPPORTED_TYPES.join(',')}
        onRemove={(file) => handleRemove(file.uid)}
        showUploadList={false}
        style={{ background: 'var(--color-paper)' }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined style={{ color: 'var(--color-moss)', fontSize: 36 }} />
        </p>
        <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--color-ink)' }}>
          点击或拖拽图片到此处
        </p>
        <p style={{ fontSize: 12, color: 'var(--color-mist)', marginTop: 4 }}>
          支持 PNG / JPEG / WebP / GIF · 单张 ≤ {MAX_SIZE_MB}MB · 最多 {maxCount} 张
        </p>
      </Upload.Dragger>

      {files.length > 0 && (
        <div
          className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2"
        >
          {files.map((f) => (
            <div
              key={f.uid}
              style={{
                position: 'relative',
                paddingTop: '100%',
                borderRadius: 8,
                overflow: 'hidden',
                border: '1px solid var(--color-line)',
                background: 'var(--color-card)',
              }}
            >
              <img
                src={f.url}
                alt={f.name}
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                }}
              />
              <button
                onClick={() => handleRemove(f.uid)}
                style={{
                  position: 'absolute',
                  top: 4,
                  right: 4,
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: 'rgba(0, 0, 0, 0.5)',
                  color: '#FFFFFF',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                aria-label="删除"
              >
                <DeleteOutlined style={{ fontSize: 12 }} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
