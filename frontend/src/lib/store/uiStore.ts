import { create } from 'zustand'

interface UIState {
  siderCollapsed: boolean
  toogleSider: () => void
  setSiderCollapsed: (collapsed: boolean) => void
}

export const useUIStore = create<UIState>((set) => ({
  siderCollapsed: false,
  toogleSider: () => set((state) => ({ siderCollapsed: !state.siderCollapsed })),
  setSiderCollapsed: (collapsed) => set({ siderCollapsed: collapsed }),
}))
