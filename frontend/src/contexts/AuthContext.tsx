import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  authApi,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  storeTokens,
  USER_KEY,
} from "../services/api";
import type { Role, User } from "../services/api";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (data: {
    name: string;
    email: string;
    phone?: string;
    password: string;
    role: string;
    district?: string;
    upazila?: string;
    business_name?: string;
  }) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? (JSON.parse(raw) as User) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me);
      localStorage.setItem(USER_KEY, JSON.stringify(me));
    } catch {
      // Token invalid and refresh (if any) failed — the interceptor clears tokens.
      if (!getAccessToken()) setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (getAccessToken()) await refreshUser();
      setLoading(false);
    })();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    storeTokens(res.access_token, res.refresh_token);
    setUser(res.user);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    return res.user;
  }, []);

  const register = useCallback(async (data: Parameters<AuthCtx["register"]>[0]) => {
    const res = await authApi.register(data);
    storeTokens(res.access_token, res.refresh_token);
    setUser(res.user);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    return res.user;
  }, []);

  const logout = useCallback(async () => {
    const rt = getRefreshToken();
    // Only call /auth/logout when we have a refresh token to revoke.
    if (rt) await authApi.logout(rt);
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refreshUser }),
    [user, loading, login, register, logout, refreshUser]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function roleHome(role: Role | string | undefined): string {
  switch (role) {
    case "admin":
      return "/admin";
    case "transporter":
      return "/deliveries";
    default:
      return "/dashboard";
  }
}
