import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  accessToken: string | null;
  userEmail: string | null;
  hydrated: boolean;
  setAuth: (token: string, email?: string | null) => void;
  clearAuth: () => void;
  setHydrated: (hydrated: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      userEmail: null,
      hydrated: false,
      setAuth: (token: string, email?: string | null) =>
        set({ accessToken: token, userEmail: email ?? null }),
      clearAuth: () => set({ accessToken: null, userEmail: null }),
      setHydrated: (hydrated: boolean) => set({ hydrated }),
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({ accessToken: state.accessToken, userEmail: state.userEmail }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    }
  )
);

export const selectIsAuthenticated = (state: AuthState): boolean => Boolean(state.accessToken);
