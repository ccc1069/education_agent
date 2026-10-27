import type { KnowledgeNode } from '@/types/api'

/** 将知识点 id 解析为中文名;图谱未加载时回退为 id */
export function knowledgeName(
  nodes: KnowledgeNode[] | undefined | null,
  id: string | null | undefined,
): string {
  if (!id) return ''
  const hit = nodes?.find((n) => n.id === id)
  return hit?.name ?? id
}

/** 批量解析知识点名称 */
export function knowledgeNames(
  nodes: KnowledgeNode[] | undefined | null,
  ids: string[] | undefined | null,
): string[] {
  if (!ids?.length) return []
  return ids.map((id) => knowledgeName(nodes, id))
}

/** 构建 id → name 映射,适合列表高频查找 */
export function buildKnowledgeNameMap(
  nodes: KnowledgeNode[] | undefined | null,
): Map<string, string> {
  const map = new Map<string, string>()
  nodes?.forEach((n) => map.set(n.id, n.name))
  return map
}

export function mapKnowledgeName(map: Map<string, string>, id: string): string {
  return map.get(id) ?? id
}
