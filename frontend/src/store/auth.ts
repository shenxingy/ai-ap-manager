import { create } from "zustand";
import { persist, StorageValue } from "zustand/middleware";

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  rememberMe: boolean;
  setAuth: (token: string, user: User, rememberMe?: boolean) => void;
  logout: () => void;
}

const customStorage = {
  getItem: (name: string): StorageValue<AuthState> | null => {
    if (typeof window === "undefined") return null;
    const stored = localStorage.getItem(name) || sessionStorage.getItem(name);
    return stored ? JSON.parse(stored) : null;
  },
  setItem: (name: string, value: StorageValue<AuthState>) => {
    if (typeof window === "undefined") return;
    const rememberMe = (value as any)?.state?.rememberMe ?? true;

    if (rememberMe) {
      localStorage.setItem(name, JSON.stringify(value));
      sessionStorage.removeItem(name);
    } else {
      sessionStorage.setItem(name, JSON.stringify(value));
      localStorage.removeItem(name);
    }
  },
  removeItem: (name: string) => {
    if (typeof window === "undefined") return;
    localStorage.removeItem(name);
    sessionStorage.removeItem(name);
  },
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      rememberMe: true,
      setAuth: (token, user, rememberMe = true) => set({ token, user, rememberMe }),
      logout: () => set({ token: null, user: null }),
    }),
    {
      name: "auth-storage",
      storage: customStorage as any,
    }
  )
);
