"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import type { SessionUser } from "@/lib/auth";

type AuthState = {
  user: SessionUser | null;
  isLoading: boolean;
  authMode: "disabled" | "mock" | "oidc";
  login: (userId: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({
  user: null,
  isLoading: true,
  authMode: "disabled",
  login: async () => null,
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [authMode, setAuthMode] = useState<"disabled" | "mock" | "oidc">("disabled");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch("/api/auth/session")
      .then((r) => r.json())
      .then((data) => {
        const mode = data.auth_mode;
        if (mode === "mock") setAuthMode("mock");
        else if (mode === "oidc") setAuthMode("oidc");
        else setAuthMode("disabled");
        if (data.authenticated && data.user) {
          setUser(data.user);
        }
      })
      .catch(() => {
        // Not authenticated or network error
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (userId: string, password: string): Promise<string | null> => {
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ user_id: userId, password }),
      });
      const data = await res.json();
      setAuthMode(data.auth_mode === "mock" ? "mock" : "disabled");
      if (!res.ok) {
        return data.detail || "Login failed";
      }
      if (data.user) {
        setUser(data.user);
      }
      return null;
    } catch {
      return "Network error";
    }
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, authMode, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
