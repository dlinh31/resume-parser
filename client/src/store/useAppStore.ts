import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

interface AppState {
  uploadStatus: 'idle' | 'uploading' | 'done' | 'error'
  activeJobId: string | null
  setUploadStatus: (status: AppState['uploadStatus']) => void
  setActiveJobId: (id: string | null) => void
}

export const useAppStore = create<AppState>()(
  devtools(
    (set) => ({
      uploadStatus: 'idle',
      activeJobId: null,
      setUploadStatus: (status) => set({ uploadStatus: status }),
      setActiveJobId: (id) => set({ activeJobId: id }),
    }),
    { name: 'AppStore' }
  )
)
