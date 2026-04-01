import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ViewModeStore {
  mode: "live" | "demo";
  setMode: (mode: "live" | "demo") => void;
  toggleMode: () => void;
}

export const useViewMode = create<ViewModeStore>()(
  persist(
    (set, get) => ({
      mode: "live",
      setMode: (mode) => set({ mode }),
      toggleMode: () => set({ mode: get().mode === "live" ? "demo" : "live" }),
    }),
    { name: "aifred-view-mode" },
  ),
);
